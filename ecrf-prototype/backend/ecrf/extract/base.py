"""The adapter.

The model is a config value, not a dependency. Switching from a hosted API
to a self-hosted model, or between vendors, is three environment variables
and no code change.
"""

from dataclasses import asdict, dataclass, field
from typing import Protocol

from ecrf.config import config
from ecrf.schema import ExtractionPlan, FormFields, VisitForm, VisitList


class ExtractionError(RuntimeError):
    """A call that must not be accepted as success: truncated output, or a
    response that stayed invalid after the retry."""


@dataclass
class Usage:
    """Token and call counters for one run. Prices turn them into money."""

    calls_made: int = 0
    calls_from_cache: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    dropped_params: list[str] = field(default_factory=list)

    def add(self, other: "Usage") -> None:
        for k in ("calls_made", "calls_from_cache", "input_tokens", "cached_input_tokens",
                  "output_tokens", "reasoning_tokens"):
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def cost_usd(self) -> float:
        fresh = max(0, self.input_tokens - self.cached_input_tokens)
        return round(
            fresh * config.price_input_per_m / 1e6
            + self.cached_input_tokens * config.price_cached_input_per_m / 1e6
            + self.output_tokens * config.price_output_per_m / 1e6, 4)

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("dropped_params")
        return {"llm_calls_made": d["calls_made"], "llm_calls_from_cache": d["calls_from_cache"],
                "input_tokens": d["input_tokens"], "cached_input_tokens": d["cached_input_tokens"],
                "output_tokens": d["output_tokens"], "reasoning_tokens": d["reasoning_tokens"],
                "est_cost_usd": self.cost_usd()}

    @classmethod
    def from_summary(cls, d: dict) -> "Usage":
        return cls(calls_made=d.get("llm_calls_made", 0), calls_from_cache=d.get("llm_calls_from_cache", 0),
                   input_tokens=d.get("input_tokens", 0), cached_input_tokens=d.get("cached_input_tokens", 0),
                   output_tokens=d.get("output_tokens", 0), reasoning_tokens=d.get("reasoning_tokens", 0))


class Extractor(Protocol):
    name: str
    model: str
    usage: Usage

    def begin_run(self, protocol_hash: str, force: bool = False) -> None:
        """Reset counters and set the per-protocol cache key. force skips
        reads from our own cache (writes still happen)."""
        ...

    def list_visits(self, protocol_text: str) -> VisitList:
        """Pass one, per_visit. The visit list is the backbone everything
        loops over, so it gets its own call rather than being folded into
        the first visit's request."""
        ...

    def plan(self, protocol_text: str) -> ExtractionPlan:
        """Pass one, per_form: visits plus the form x visit schedule."""
        ...

    def fields_for_visit(self, protocol_text: str, visit: str,
                         visits: list[str]) -> VisitForm:
        """Pass two, once per visit. Prompt order is load bearing for
        caching: stable prefix first, varying question last."""
        ...

    def fields_for_form(self, protocol_text: str, form: str, form_visits: list[str],
                        visits: list[str]) -> FormFields:
        """Pass two, per_form: one call per form, fields defined once."""
        ...


def get_extractor(backend: str | None = None) -> Extractor:
    backend = backend or config.backend
    if backend == "mock":
        from ecrf.extract.mock import MockExtractor
        return MockExtractor()
    if backend == "openai_compat":
        from ecrf.extract.openai_compat import OpenAICompatExtractor
        return OpenAICompatExtractor(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_output_tokens=config.max_output_tokens,
            reasoning_effort=config.reasoning_effort,
            provider_cache=config.provider_cache,
        )
    raise ValueError(f"unknown ECRF_BACKEND: {backend}")
