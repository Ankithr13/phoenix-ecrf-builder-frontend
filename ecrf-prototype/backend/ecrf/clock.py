"""The one place the app reads the time.

Every timestamp written to a row and every comparison against today asks
here. The demo seed sets the clock before each step, so a study's story can be
told over several weeks through the real endpoints instead of editing
timestamps afterwards. Nothing else sets it."""

from datetime import UTC, date, datetime

_fixed: datetime | None = None


def now() -> datetime:
    """Naive UTC. SQLite drops the timezone on the way in, so comparing a
    stored value against an aware datetime raises; everything is naive UTC
    on both sides instead."""
    return _fixed if _fixed is not None else datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return now().date()


def set_to(at: datetime | None) -> None:
    """Fix the clock at a naive UTC moment, or None to follow real time again."""
    global _fixed
    if at is not None and at.tzinfo is not None:
        raise ValueError("the clock is naive UTC")
    _fixed = at
