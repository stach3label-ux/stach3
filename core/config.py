"""Vektra Open - free-tier configuration.

Every value comes from environment variables / a project-root .env file.
Nothing secret is ever committed; see .env.example for the full list.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    def load_dotenv(*_args, **_kwargs):  # type: ignore[no-redef]
        return None

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)


# ── required ─────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ── HTTP server ──────────────────────────────────────────────────────────────
HEALTH_HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
try:
    PORT = int(os.getenv("PORT", os.getenv("HEALTH_PORT", "7860")))
except ValueError:
    PORT = 7860

# Shared secret the site sends with /receipt (optional, empty disables check)
CHECKOUT_RECEIPT_SECRET = os.getenv("CHECKOUT_RECEIPT_SECRET", "").strip()

# ── Postgres ─────────────────────────────────────────────────────────────────
DB_TIMEOUT_SECONDS = 8

# ── Lavalink (music, fully optional) ────────────────────────────────────────
LAVALINK_HOST = os.getenv("LAVALINK_HOST", "127.0.0.1").strip()
try:
    LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", "2333"))
except ValueError:
    LAVALINK_PORT = 2333
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "").strip()
LAVALINK_IDENTIFIER = os.getenv("LAVALINK_IDENTIFIER", "vektra-open").strip()
LAVALINK_SSL = os.getenv("LAVALINK_SSL", "0").lower() not in {"0", "false", "no"}
MAX_TRACKS_PER_REQUEST = 10

# Master music switch. True (default) = load music commands and look for
# Lavalink; False = the music cog is never loaded and Lavalink is never touched.
MUSIC_ENABLED = os.getenv("MUSIC_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}

# ── single-server lock (open-source edition is not for commercial use) ──────
# The bot permanently binds itself to the first server it joins (or to this
# guild when set). Any other server is left automatically. Multi-server /
# commercial use requires a proper fork.
try:
    GUILD_ID = int(os.getenv("GUILD_ID", "0"))
except ValueError:
    GUILD_ID = 0

# ── AI MCP server (optional) ─────────────────────────────────────────────────
# When MCP_PASSWORD is set, the bot serves a Model Context Protocol endpoint at
# http://<host>:<PORT>/mcp. AI assistants connect through the OAuth connector
# flow where the user just enters this password — no Discord login, no server
# selection (the bot is single-server). Leave empty to disable the MCP server.
MCP_PASSWORD = os.getenv("MCP_PASSWORD", "").strip()
# Access tokens 4h, refresh tokens 30d, authorization codes 10 min.
MCP_ACCESS_TOKEN_TTL = 4 * 60 * 60
MCP_REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60
MCP_AUTH_CODE_TTL = 10 * 60
MCP_NAME = "vektra-open"
MCP_VERSION = "1.0.0"

# ── AI spam screening (fully optional; one key is enough) ───────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "").strip()
SAMBANOVA_API_URL = os.getenv("SAMBANOVA_API_URL", "https://api.sambanova.ai/v1/chat/completions").strip()
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.1-8B-Instruct").strip()

# ── behaviour constants (no env, safe to tweak) ─────────────────────────────
COOLDOWN_MINUTES = 30
PAGE_SIZE = 5
TICKET_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I

LABEL_STATUSES = ["In Queue", "Approved", "Rejected"]
TICKET_STATUSES = ["Open", "Waiting", "Answered", "Resolved"]

COLOR_BLURPLE = 0x5865F2
COLOR_GREEN = 0x43B581
COLOR_RED = 0xF04747
COLOR_GOLD = 0xF1C40F

DEFAULT_PRESENCE_TEXT = "listening to /submit"
BOT_COMMUNITY_LINK = "https://github.com/Dap69420/vektra-open"

TEXT_INPUT_LIMITS = {
    "real_name": 100,
    "track_name": 100,
    "demo_link": 500,
    "artists": 300,
    "message": 700,
    "email": 200,
}


def ai_spam_provider() -> dict:
    """Pick an AI provider for spam screening based on which key is set.

    Returns a dict with api_url / model / api_key or an empty dict when no
    provider is configured (screening is then skipped).
    """
    if SAMBANOVA_API_KEY:
        return {"name": "sambanova", "api_url": SAMBANOVA_API_URL, "model": SAMBANOVA_MODEL, "api_key": SAMBANOVA_API_KEY}
    if GROQ_API_KEY:
        return {"name": "groq", "api_url": GROQ_API_URL, "model": GROQ_MODEL, "api_key": GROQ_API_KEY}
    if OPENAI_API_KEY:
        return {"name": "openai", "api_url": OPENAI_API_URL, "model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
    return {}
