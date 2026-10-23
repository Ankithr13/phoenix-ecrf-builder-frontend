"""FastAPI application. Run with:  uvicorn ecrf.api.app:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecrf import __version__
from ecrf.api import auth, dashboard, data, protocols, studies
from ecrf.config import config
from ecrf.storage import db, migrate

log = logging.getLogger("ecrf")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The schema is owned by Alembic now. Starting on a database that is
    # behind would surface as bare 500s on the first query, so refuse here
    # with the command that fixes it.
    migrate.assert_up_to_date(db._engine)
    log.info("ecrf %s backend=%s model=%s db=%s", __version__, config.backend,
             config.llm_model if config.backend != "mock" else "recorded",
             config.database_url.split("://", 1)[0])
    yield


app = FastAPI(title="eCRF Pipeline", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(protocols.router)
app.include_router(studies.router)
app.include_router(data.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "backend": config.backend,
            "model": config.llm_model if config.backend != "mock" else "recorded",
            "context_mode": config.context_mode,
            "quote_match_threshold": config.quote_match_threshold}
