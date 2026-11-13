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


DEV_SECRET_KEY = "dev-secret-not-for-production"


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
    # set. Prices are per million tokens and come only from the environment:
    # a missing one shows as "not configured", never as a wrong number.
    max_output_tokens: int
    reasoning_effort: str
    provider_cache: bool
    price_input_per_m: float | None
    price_cached_input_per_m: float | None
    price_output_per_m: float | None
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

    # dev or prod. Prod turns the API docs off, forces Secure cookies, and
    # refuses to start without a real SECRET_KEY.
    env: str
    secret_key: str
    seed_demo: bool
    # Wrong passwords allowed per account in 15 minutes before sign-in is
    # refused. 0 turns the limit off, for a demo where people share a password.
    login_max_failures: int = 5


def _price(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else None


def database_url(raw: str) -> str:
    """Supabase, Neon and Railway hand out postgres:// or postgresql:// URLs.
    SQLAlchemy needs the driver named, and psycopg 3 is the one installed."""
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw.removeprefix(prefix)
    return raw


def load() -> Config:
    env = os.getenv("ECRF_ENV", "dev")
    return Config(
        backend=os.getenv("ECRF_BACKEND", "mock"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-6-luna"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        context_mode=os.getenv("ECRF_CONTEXT", "auto"),
        context_token_limit=int(os.getenv("ECRF_CONTEXT_TOKEN_LIMIT", "60000")),
        quote_match_threshold=int(os.getenv("QUOTE_MATCH_THRESHOLD", "90")),
        max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "16000")),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "none"),
        provider_cache=os.getenv("LLM_PROVIDER_CACHE", "true").lower() == "true",
        price_input_per_m=_price("LLM_PRICE_INPUT_PER_M"),
        price_cached_input_per_m=_price("LLM_PRICE_CACHED_PER_M"),
        price_output_per_m=_price("LLM_PRICE_OUTPUT_PER_M"),
        extract_strategy=os.getenv("EXTRACT_STRATEGY", "per_visit"),
        database_url=database_url(os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{ROOT / 'ecrf.db'}"),
        data_dir=Path(os.getenv("ECRF_DATA_DIR", ROOT / "data")),
        # Separate from data_dir so tests can upload into a temporary folder
        # without losing the bundled sample and library that live in data/.
        upload_dir=Path(os.getenv("ECRF_UPLOAD_DIR", ROOT / "data" / "uploads")),
        session_hours=int(os.getenv("SESSION_HOURS", "12")),
        cookie_secure=env == "prod" or os.getenv("COOKIE_SECURE", "false").lower() == "true",
        demo_password=os.getenv("DEMO_PASSWORD", "demo1234"),
        env=env,
        secret_key=os.getenv("SECRET_KEY", "" if env == "prod" else DEV_SECRET_KEY),
        seed_demo=os.getenv("SEED_DEMO", "") == "1",
        login_max_failures=int(os.getenv("LOGIN_MAX_FAILURES", "5")),
    )


def check_production(cfg: Config) -> None:
    """Called at startup. A deployment with the development key could have
    its session hashes recomputed by anyone who has read this file."""
    if cfg.env == "prod" and (not cfg.secret_key or cfg.secret_key == DEV_SECRET_KEY):
        raise RuntimeError("ECRF_ENV=prod needs SECRET_KEY set to a private value")


def docs_settings(cfg: Config) -> dict:
    """FastAPI's interactive docs are off in production."""
    if cfg.env == "prod":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


config = load()
