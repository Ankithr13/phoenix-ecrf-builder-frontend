"""One backend for every provider that speaks the OpenAI chat format.

    OpenAI       LLM_BASE_URL=https://api.openai.com/v1
    vLLM (SCC)   LLM_BASE_URL=http://localhost:8000/v1
    Groq         LLM_BASE_URL=https://api.groq.com/openai/v1
    OpenRouter   LLM_BASE_URL=https://openrouter.ai/api/v1
    Gemini       LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

What every call does, in order:
  1. look the exact request up in our own cache (ecrf.extract.cache); a hit
     costs nothing and is counted as a call from cache
  2. send it with an output cap, JSON mode, reasoning effort and OpenAI's
     prompt-cache hints; any parameter the provider rejects is dropped,
     logged once, and never sent again by this extractor
  3. refuse a truncated answer (finish_reason == "length") outright
  4. read resp.usage into the run's counters and store the answer in the
     cache

JSON is validated with Pydantic; one retry feeds the validation error back.
"""

import json
import logging
import re

from openai import BadRequestError, OpenAI
from pydantic import ValidationError

from ecrf.extract import cache, prompts
from ecrf.extract.base import ExtractionError, Usage
from ecrf.schema import ExtractionPlan, FieldDef, FormFields, VisitForm, VisitList

log = logging.getLogger("ecrf.llm")

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_JSON_MODE = {"type": "json_object"}
_OPENAI_HOSTS = {"api.openai.com"}


class OpenAICompatExtractor:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.0,
                 max_output_tokens: int = 16000, reasoning_effort: str = "",
                 provider_cache: bool = True):
        if not api_key and "localhost" not in base_url and "127.0.0.1" not in base_url:
            raise RuntimeError("LLM_API_KEY is not set")
        # The SDK backs off on 429 and 5xx by itself with max_retries set.
        self.client = OpenAI(base_url=base_url, api_key=api_key or "none", max_retries=3)
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort or None
        self.provider_cache = provider_cache and cache.host_of(base_url) in _OPENAI_HOSTS
        self.usage = Usage()
        self._unsupported: set[str] = set()
        self._use_old_max_tokens = False
        self._cache_key_hint: str | None = None
        self._bypass_cache = False

    # ------------------------------------------------------------- run
    def begin_run(self, protocol_hash: str, force: bool = False) -> None:
        self.usage = Usage()
        self.invalid_fields: list[dict] = []
        self._cache_key_hint = f"ecrf-{protocol_hash[:16]}" if protocol_hash else None
        self._bypass_cache = force

    # -------------------------------------------------------- internals
    def _optional_kwargs(self) -> dict:
        kw: dict = {}
        if "response_format" not in self._unsupported:
            kw["response_format"] = _JSON_MODE
        if self.max_output_tokens:
            if self._use_old_max_tokens:
                if "max_tokens" not in self._unsupported:
                    kw["max_tokens"] = self.max_output_tokens
            elif "max_completion_tokens" not in self._unsupported:
                kw["max_completion_tokens"] = self.max_output_tokens
        if self.reasoning_effort and "reasoning_effort" not in self._unsupported:
            kw["reasoning_effort"] = self.reasoning_effort
        extra = {}
        if self.provider_cache and self._cache_key_hint:
            if "prompt_cache_key" not in self._unsupported:
                extra["prompt_cache_key"] = self._cache_key_hint
            if "prompt_cache_retention" not in self._unsupported:
                extra["prompt_cache_retention"] = "24h"
        if extra:
            kw["extra_body"] = extra
        return kw

    def _drop_rejected(self, message: str) -> bool:
        """Work out which optional parameter the provider refused, remember
        it, and say whether the call is worth repeating."""
        msg = message.lower()
        if "max_completion_tokens" in msg and not self._use_old_max_tokens:
            # Older compat servers only know the previous name.
            self._use_old_max_tokens = True
            log.warning("provider rejected max_completion_tokens; retrying with max_tokens")
            return True
        for name in ("response_format", "max_tokens", "reasoning_effort",
                     "prompt_cache_key", "prompt_cache_retention"):
            if name in msg and name not in self._unsupported:
                self._unsupported.add(name)
                self.usage.dropped_params.append(name)
                log.warning("provider rejected %s; dropped for the rest of this process", name)
                return True
        return False

    def _record_usage(self, resp) -> dict:
        u = getattr(resp, "usage", None)
        prompt = getattr(u, "prompt_tokens", 0) or 0
        completion = getattr(u, "completion_tokens", 0) or 0
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        return {"prompt_tokens": prompt, "completion_tokens": completion,
                "cached_tokens": cached, "reasoning_tokens": reasoning}

    def _count(self, usage: dict, from_cache: bool) -> None:
        if from_cache:
            self.usage.calls_from_cache += 1
            return
        self.usage.calls_made += 1
        self.usage.input_tokens += usage.get("prompt_tokens", 0)
        self.usage.cached_input_tokens += usage.get("cached_tokens", 0)
        self.usage.output_tokens += usage.get("completion_tokens", 0)
        self.usage.reasoning_tokens += usage.get("reasoning_tokens", 0)

    def _chat(self, messages: list[dict]) -> str:
        key = cache.key_for(self.base_url, self.model, self.temperature, self.reasoning_effort,
                            _JSON_MODE, self.max_output_tokens, messages)
        if not self._bypass_cache:
            hit = cache.get(key)
            if hit is not None:
                text, usage = hit
                self._count(usage, from_cache=True)
                return text

        base = {"model": self.model, "messages": messages, "temperature": self.temperature}
        for _ in range(8):
            try:
                resp = self.client.chat.completions.create(**base, **self._optional_kwargs())
                break
            except BadRequestError as e:
                if not self._drop_rejected(str(e)):
                    raise
        else:
            raise ExtractionError("provider kept rejecting request parameters")

        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            raise ExtractionError(
                f"the model's answer was cut off at {self.max_output_tokens} output tokens, so it "
                f"cannot be trusted as JSON. Raise LLM_MAX_OUTPUT_TOKENS or use the per_form strategy.")
        text = choice.message.content or ""
        usage = self._record_usage(resp)
        self._count(usage, from_cache=False)
        log.info("llm call model=%s in=%s cached=%s out=%s reasoning=%s", self.model,
                 usage["prompt_tokens"], usage["cached_tokens"], usage["completion_tokens"],
                 usage["reasoning_tokens"])
        cache.put(key, self.model, messages, text, usage)
        return text

    def _json(self, messages: list[dict], model_cls):
        raw = self._chat(messages)
        try:
            return model_cls.model_validate(json.loads(_FENCE.sub("", raw).strip()))
        except (json.JSONDecodeError, ValidationError) as e:
            retry = [
                *messages,
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"That response was invalid: {e}\n"
                    "Return ONLY a corrected JSON object matching the schema."
                )},
            ]
            raw2 = self._chat(retry)
            try:
                return model_cls.model_validate(json.loads(_FENCE.sub("", raw2).strip()))
            except (json.JSONDecodeError, ValidationError) as e2:
                salvaged = self._salvage(raw2, model_cls) or self._salvage(raw, model_cls)
                if salvaged is not None:
                    return salvaged
                raise ExtractionError(f"model returned invalid JSON twice: {e2}") from e2

    def _salvage(self, raw: str, model_cls):
        """A whole visit used to be lost because one field was malformed,
        typically a quote under 20 characters copied from a table cell. Keep
        the fields that validate on their own and record the ones that do
        not, so the pipeline can log them as rejections instead of failing
        the run. None when the answer is not even a JSON object with fields."""
        try:
            obj = json.loads(_FENCE.sub("", raw).strip())
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict) or not isinstance(obj.get("fields"), list):
            return None
        kept, bad = [], []
        for item in obj["fields"]:
            try:
                FieldDef.model_validate(item)
                kept.append(item)
            except ValidationError as e:
                src = item.get("source") if isinstance(item, dict) else None
                src = src if isinstance(src, dict) else {}
                reason = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
                bad.append({"name": str(item.get("name", "?")) if isinstance(item, dict) else "?",
                            "quote": str(src.get("quote", "")), "section": str(src.get("section", "")),
                            "reason": reason})
        try:
            out = model_cls.model_validate({**obj, "fields": kept})
        except ValidationError:
            return None
        self.invalid_fields.extend(bad)
        log.warning("salvaged %s fields, dropped %s invalid: %s", len(kept), len(bad),
                    [(b["name"], b["reason"]) for b in bad])
        return out

    # ---------------------------------------------------------- interface
    def list_visits(self, protocol_text: str) -> VisitList:
        return self._json(prompts.visits_messages(protocol_text), VisitList)

    def plan(self, protocol_text: str) -> ExtractionPlan:
        return self._json(prompts.plan_messages(protocol_text), ExtractionPlan)

    def fields_for_visit(self, protocol_text: str, visit: str, visits: list[str]) -> VisitForm:
        return self._json(prompts.fields_messages(protocol_text, visit, visits), VisitForm)

    def fields_for_form(self, protocol_text: str, form: str, form_visits: list[str],
                        visits: list[str]) -> FormFields:
        return self._json(prompts.form_fields_messages(protocol_text, form, form_visits, visits),
                          FormFields)
