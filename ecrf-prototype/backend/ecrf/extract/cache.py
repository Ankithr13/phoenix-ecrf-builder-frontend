"""Our own result cache: never pay twice for the same request.

The key is the sha256 of everything that could change the answer, so a
different model, temperature or prompt is a different row and an identical
request is served from the database in milliseconds for nothing."""

import hashlib
import json
from urllib.parse import urlparse

from sqlalchemy import select

from ecrf.storage import db
from ecrf.storage.models import LLMCall


def host_of(base_url: str) -> str:
    return urlparse(base_url).hostname or base_url


def key_for(base_url: str, model: str, temperature: float, reasoning_effort: str | None,
            response_format: dict | None, max_tokens: int | None, messages: list[dict]) -> str:
    payload = {
        "base_url_host": host_of(base_url), "model": model, "temperature": temperature,
        "reasoning_effort": reasoning_effort, "response_format": response_format,
        "max_tokens": max_tokens, "messages": messages,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get(key: str) -> tuple[str, dict] | None:
    with db.session() as s:
        row = s.scalars(select(LLMCall).where(LLMCall.key == key)).first()
        if row is None:
            return None
        row.hits += 1
        return row.response_text, dict(row.usage_json)


def put(key: str, model: str, messages: list[dict], response_text: str, usage: dict) -> None:
    with db.session() as s:
        if s.scalars(select(LLMCall).where(LLMCall.key == key)).first():
            return
        s.add(LLMCall(key=key, model=model, request_json={"messages": messages},
                      response_text=response_text, usage_json=usage))
