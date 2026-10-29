"""Runtime configuration, read from the environment.

The extraction backend is a config value on purpose. Which LLM service is
approved is still an open question with the client, so nothing outside
ecrf/extract/ names a vendor.

Every provider we might use speaks the OpenAI chat-completions format
(OpenAI, vLLM, Groq, OpenRouter, Gemini's compat endpoint), so one backend
covers all of them and the difference is three env vars.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


@dataclass(frozen=True)
class Config:
    # "mock" replays a recorded fixture and needs no key. "openai_compat"
    # talks to whatever LLM_BASE_URL points at.
    backend: str

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float

    # "full" sends the whole protocol, "sections" sends only relevant
    # sections, "auto" picks by size.
    context_mode: str
    context_token_limit: int

    # Fuzzy match threshold for quote grounding. PLACEHOLDER until tuned
    # against the answer key. Single most consequential number here.
    quote_match_threshold: int

    # Cost controls. Output is capped so a runaway answer cannot bill ten
    # dollars; reasoning tokens bill as output, so effort is sent only when
    # set. Prices are per million tokens and WILL go stale; they are the
    # gpt-6-luna list prices as of October 2026.
    max_output_tokens: int
    reasoning_effort: str
    provider_cache: bool
    price_input_per_m: float
    price_cached_input_per_m: float
    price_output_per_m: float
    # per_visit: one call per visit. per_form: one call per assessment form
    # and the forms are expanded onto visits in code (fewer, shorter calls).
    extract_strategy: str

    database_url: str
    data_dir: Path
    upload_dir: Path

    # Sessions. The cookie is httpOnly and SameSite=Lax; Secure is off by
    # default because dev runs on plain http through the Vite proxy.
    session_hours: int
    cookie_secure: bool
    demo_password: str


def load() -> Config:
    return Config(
        backend=os.getenv("ECRF_BACKEND", "mock"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        context_mode=os.getenv("ECRF_CONTEXT", "auto"),
        context_token_limit=int(os.getenv("ECRF_CONTEXT_TOKEN_LIMIT", "60000")),
        quote_match_threshold=int(os.getenv("QUOTE_MATCH_THRESHOLD", "90")),
        max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "16000")),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "none"),
        provider_cache=os.getenv("LLM_PROVIDER_CACHE", "true").lower() == "true",
        price_input_per_m=float(os.getenv("PRICE_INPUT_PER_M", "0.10")),
        price_cached_input_per_m=float(os.getenv("PRICE_CACHED_INPUT_PER_M", "0.01")),
        price_output_per_m=float(os.getenv("PRICE_OUTPUT_PER_M", "0.50")),
        extract_strategy=os.getenv("EXTRACT_STRATEGY", "per_visit"),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'ecrf.db'}"),
        data_dir=Path(os.getenv("ECRF_DATA_DIR", ROOT / "data")),
        # Separate from data_dir so tests can upload into a temporary folder
        # without losing the bundled sample and library that live in data/.
        upload_dir=Path(os.getenv("ECRF_UPLOAD_DIR", ROOT / "data" / "uploads")),
        session_hours=int(os.getenv("SESSION_HOURS", "12")),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        demo_password=os.getenv("DEMO_PASSWORD", "demo1234"),
    )


config = load()
