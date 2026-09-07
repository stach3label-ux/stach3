"""Small shared text/discord formatting helpers (stdlib only)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse


def truncate_text(value, limit: int = 900) -> str:
    """Safe string for embed fields - never None, hard-capped length."""
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clean_text(value, limit: int = 900) -> str:
    """Collapse whitespace/newlines into single spaces, then truncate."""
    if value is None:
        return ""
    return truncate_text(" ".join(str(value).split()), limit)


def is_valid_url(value) -> bool:
    """True when value looks like an http(s) URL with a host."""
    if not value:
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_valid_email(value) -> bool:
    if not value:
        return False
    text = str(value).strip()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text))


def parse_ticket_code(value) -> str:
    """Normalise a ticket code typed by a user (``ABC123`` -> ABC123)."""
    if not value:
        return ""
    return str(value).strip().strip("`").strip().upper()


def discord_timestamp(value) -> str:
    """Render a datetime as a Discord <t:...> timestamp, or '' when missing."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return f"<t:{int(value.timestamp())}:f>"
    try:
        stamp = int(value)
        return f"<t:{stamp}:f>"
    except (TypeError, ValueError):
        return ""


def format_duration(seconds) -> str:
    """1:23 or 1:02:03, or 'Unknown'."""
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
