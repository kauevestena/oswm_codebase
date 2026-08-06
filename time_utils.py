"""Timezone-safe timestamp helpers shared by OSWM node jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LEGACY_FORMATS = ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime | None = None) -> str:
    """Serialize *value* as an ISO-8601 UTC timestamp with a ``Z`` suffix."""

    value = value or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_timestamp(value: object, legacy_timezone: str = "UTC") -> datetime | None:
    """Parse current ISO timestamps and the historical OSWM local-time format.

    Legacy values did not carry an offset.  They are interpreted in the node's
    configured timezone before conversion to UTC; this prevents the old local
    wall-clock value from silently being treated as UTC.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        legacy_zone = ZoneInfo(legacy_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        legacy_zone = timezone.utc
    for pattern in LEGACY_FORMATS:
        try:
            return datetime.strptime(raw, pattern).replace(
                tzinfo=legacy_zone
            ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None
