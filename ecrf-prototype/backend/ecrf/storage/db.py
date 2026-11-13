import os
from contextlib import contextmanager

from sqlalchemy import NullPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ecrf.config import config
from ecrf.storage.models import ECRFVersion, Protocol


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    options = {
        # Supabase's transaction pooler (port 6543) cannot keep prepared
        # statements between transactions, so psycopg must not make any.
        "connect_args": {"prepare_threshold": None},
        "pool_pre_ping": True,
    }
    if os.getenv("VERCEL"):
        # A serverless instance can be frozen between requests. Holding no
        # connection open leaves the pooler to do the pooling.
        options["poolclass"] = NullPool
    return options


_engine = create_engine(config.database_url, **_engine_options(config.database_url))
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def session() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def latest_version(s: Session, protocol_id: int) -> ECRFVersion | None:
    return s.scalars(
        select(ECRFVersion)
        .where(ECRFVersion.protocol_id == protocol_id)
        .order_by(ECRFVersion.version.desc())
        .limit(1)
    ).first()


def save_version(s: Session, protocol: Protocol, content: dict, created_by: str,
                 note: str | None = None) -> ECRFVersion:
    """Insert a NEW version row. Never updates an existing one."""
    prev = latest_version(s, protocol.id)
    v = ECRFVersion(
        protocol_id=protocol.id,
        protocol_hash=protocol.text_hash,
        version=(prev.version + 1) if prev else 1,
        content=content,
        created_by=created_by,
        note=note,
    )
    s.add(v)
    s.flush()
    return v


def locked_version(s: Session, protocol_id: int) -> ECRFVersion | None:
    """The locked version, if the protocol is locked. Review and extraction
    refuse once a version is locked, so it is always also the latest."""
    v = latest_version(s, protocol_id)
    return v if v and v.state == "locked" else None
