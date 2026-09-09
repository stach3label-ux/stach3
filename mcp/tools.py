"""MCP tool specifications and dispatcher for Vektra Open.

Tools operate on the bot's single locked server. There is no approval flow
and no policy filter on this server: the AI assistant is the only reviewer
of what it creates — the tool descriptions tell it to refuse only genuinely
serious requests. Everything that acts on Discord members is still
permission-gated at runtime by Discord itself (the member running the
command must hold the matching permission; the bot never elevates anyone).
"""

from __future__ import annotations

import asyncio
import re
import threading
from datetime import datetime, timezone

from core import database as store

_bot = None
_locked_guild_id = 0
_bind_lock = threading.Lock()

NAME_RE = re.compile(r"^[a-z0-9_]{2,32}$")
PARAM_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")

ALLOWED_PARAM_TYPES = {"string", "integer", "boolean", "user", "channel"}

ALLOWED_ACTIONS = [
    "text_reply",
    "lookup_submission",
    "my_submissions",
    "random_pick",
    "show_link",
    "give_role",
    "remove_role",
    "kick_member",
    "ban_member",
    "timeout_member",
    "announce",
    "webhook_post",
]

MEMBER_ACTIONS = {"kick_member", "ban_member", "timeout_member"}
ROLE_ACTIONS = {"give_role", "remove_role"}

TICKET_STATUSES = ["Open", "Waiting", "Answered", "Resolved"]

AUTHORING_POLICY = (
    "You are the ONLY reviewer of commands you create here. There is no approval step and no "
    "server-side content filter: commands go LIVE on the Discord server immediately. So judge "
    "every request yourself and refuse only the genuinely serious: anything illegal, breaking "
    "Discord ToS, credential/password/token/OTP harvesting, phishing or fake verification flows, "
    "prize-bait scams ('you won', 'claim your gift'), or mass-DM advertising. Everything else is "
    "allowed — including powerful moderation, role management, announcements and webhook "
    "integrations; that power is exactly the point. Always write an honest user_impact_summary "
    "of what the command does and who it can affect. Commands are declarative manifests — they "
    "can never run arbitrary code. Every role/moderation action is checked against the Discord "
    "permissions of whoever runs the command at runtime."
)


def bind_bot(bot) -> None:
    with _bind_lock:
        global _bot
        _bot = bot


def set_locked_guild(guild_id: int) -> None:
    global _locked_guild_id
    _locked_guild_id = int(guild_id or 0)


def _bot_ready() -> tuple[bool, str]:
    if _bot is None:
        return False, "The bot is still starting up. Try again in a minute."
    if not _locked_guild_id:
        return False, "The bot has not joined a server yet, so there is nothing to manage."
    return True, ""


def _run_coro(coro, timeout: float = 15.0):
    """Run a coroutine on the bot's loop from the HTTP thread."""
    loop = _bot.loop
    if loop is None or loop.is_closed():
        raise RuntimeError("Bot event loop is not running.")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _notify_custom_commands() -> None:
    """Nudge the custom-commands cog to re-sync soon instead of waiting a minute."""
    event = getattr(_bot, "custom_commands_refresh", None)
    if event is None:
        return

    async def _set():
        event.set()

    try:
        _run_coro(_set(), timeout=5)
    except Exception:
        pass


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value) if value is not None else ""


# ── manifest validation (structural only — what the interpreter can run) ─────


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object."]

    name = str(manifest.get("name") or "").strip()
    if not NAME_RE.match(name):
        errors.append("name must be 2-32 chars: lowercase letters, digits, underscores.")

    description = str(manifest.get("description") or "").strip()
    if not description or len(description) > 100:
        errors.append("description is required (max 100 characters).")

    params = manifest.get("parameters")
    params = params if isinstance(params, list) else []
    if len(params) > 5:
        errors.append("at most 5 parameters are allowed.")
    seen = set()
    for p in params:
        pname = str((p or {}).get("name") or "").strip()
        if not PARAM_NAME_RE.match(pname):
            errors.append(f"parameter '{pname}' has an invalid name.")
        if pname in seen:
            errors.append(f"duplicate parameter '{pname}'.")
        seen.add(pname)
        ptype = str((p or {}).get("type") or "string")
        if ptype not in ALLOWED_PARAM_TYPES:
            errors.append(f"parameter '{pname}' type must be one of: {', '.join(sorted(ALLOWED_PARAM_TYPES))}.")

    response = manifest.get("response")
    response = response if isinstance(response, dict) else {}
    content = response.get("content")
    embed = response.get("embed")
    if content is not None and len(str(content)) > 2000:
        errors.append("response.content max length is 2000.")
    if isinstance(embed, dict):
        if embed.get("title") is not None and len(str(embed["title"])) > 256:
            errors.append("response.embed.title max length is 256.")
        if embed.get("description") is not None and len(str(embed["description"])) > 4000:
            errors.append("response.embed.description max length is 4000.")
    if not content and not (isinstance(embed, dict) and (embed.get("title") or embed.get("description"))):
        errors.append("response must define content or an embed (title/description).")

    actions = manifest.get("actions")
    actions = actions if isinstance(actions, list) else []
    if not actions:
        errors.append("at least one action is required.")
    if len(actions) > 10:
        errors.append("at most 10 actions are allowed.")
    for action in actions:
        action = action or {}
        atype = str(action.get("type") or "")
        if atype not in ALLOWED_ACTIONS:
            errors.append(f"action type '{atype}' is not supported. Supported: {', '.join(ALLOWED_ACTIONS)}.")
            continue
        if len(str(action.get("input") or "")) > 500:
            errors.append(f"action {atype} input max length is 500.")
        if len(str(action.get("body") or "")) > 2000:
            errors.append(f"action {atype} body max length is 2000.")
        store_as = action.get("store_as")
        if store_as and not PARAM_NAME_RE.match(str(store_as)):
            errors.append(f"action {atype} store_as must be snake_case (max 32 chars).")
        if atype in MEMBER_ACTIONS and not any(str((p or {}).get("type")) == "user" for p in params):
            errors.append(f"action {atype} needs a parameter of type 'user' so the command can target a member.")
        if atype in ROLE_ACTIONS and not str(action.get("input") or "").strip():
            errors.append(f"action {atype} needs a role name or ID in input.")

    rate_limit = manifest.get("rate_limit")
    rate_limit = rate_limit if isinstance(rate_limit, dict) else {}
    try:
        max_uses = int(rate_limit.get("max_uses_per_user_hour", 5))
    except (TypeError, ValueError):
        max_uses = -1
    if not 1 <= max_uses <= 30:
        errors.append("rate_limit.max_uses_per_user_hour must be an integer between 1 and 30.")

    return errors


# ── tool implementations ─────────────────────────────────────────────────────


def _tool_create_command(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    manifest = args.get("manifest")
    if not isinstance(manifest, dict):
        return {"error": "manifest object is required.", "policy": AUTHORING_POLICY}
    errors = validate_manifest(manifest)
    if errors:
        return {"error": "Manifest failed structural validation.", "validation": errors, "policy": AUTHORING_POLICY}
    name = str(manifest["name"]).strip().lower()
    store.upsert_custom_command(_locked_guild_id, name, manifest, created_by="mcp")
    _notify_custom_commands()
    return {
        "ok": True,
        "name": name,
        "status": "live",
        "note": "Command is live (or updated) and will appear in Discord within a few seconds. Tell the user it may take a moment to show up in their client.",
        "policy": AUTHORING_POLICY,
    }


def _tool_list_commands(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    rows = store.list_custom_commands(_locked_guild_id)
    return {
        "commands": [
            {
                "name": r["name"],
                "enabled": r["enabled"],
                "description": (r["manifest"] or {}).get("description", ""),
                "created_by": r["created_by"],
                "updated_at": _iso(r["updated_at"]),
            }
            for r in rows
        ]
    }


def _tool_get_command(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    name = str(args.get("name") or "").strip().lower()
    row = store.get_custom_command(_locked_guild_id, name)
    if not row:
        return {"error": f"No command named '{name}'."}
    usage = store.custom_command_usage_summary(_locked_guild_id, name)
    return {
        "name": row["name"],
        "enabled": row["enabled"],
        "manifest": row["manifest"],
        "created_by": row["created_by"],
        "updated_at": _iso(row["updated_at"]),
        "usage": usage,
    }


def _tool_delete_command(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    name = str(args.get("name") or "").strip().lower()
    if not store.delete_custom_command(_locked_guild_id, name):
        return {"error": f"No command named '{name}'."}
    _notify_custom_commands()
    return {"ok": True, "deleted": name}


def _tool_set_command_enabled(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    name = str(args.get("name") or "").strip().lower()
    enabled = bool(args.get("enabled", True))
    if not store.set_custom_command_enabled(_locked_guild_id, name, enabled):
        return {"error": f"No command named '{name}'."}
    _notify_custom_commands()
    return {"ok": True, "name": name, "enabled": enabled}


def _submission_brief(row: dict) -> dict:
    return {
        "code": row["ticket_code"],
        "artist_name": row["artist_name"],
        "artist_id": row["artist_id"],
        "track_name": row["track_name"],
        "artists": row.get("artists") or "",
        "demo_link": row["demo_link"],
        "message": row.get("message") or "",
        "status": row["status"],
        "reason": row.get("reason") or "",
        "spam_flagged": bool(row.get("spam_flagged")),
        "created_at": _iso(row.get("created_at")),
        "decided_at": _iso(row.get("decided_at")),
    }


def _tool_list_submissions(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    status = str(args.get("status") or "").strip() or None
    try:
        limit = max(1, min(int(args.get("limit") or 10), 50))
    except (TypeError, ValueError):
        limit = 10
    rows = store.list_submissions(_locked_guild_id, status=status, limit=limit)
    total = store.count_submissions(_locked_guild_id, status=status)
    return {"total": total, "submissions": [_submission_brief(r) for r in rows]}


def _tool_get_submission(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    code = str(args.get("code") or "").strip()
    row = store.fetch_submission(_locked_guild_id, code)
    if not row:
        return {"error": f"No submission with code '{code.upper()}'."}
    return _submission_brief(row)


def _tool_decide_submission(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    code = str(args.get("code") or "").strip()
    decision = str(args.get("decision") or "").strip().lower()
    reason = str(args.get("reason") or "").strip() or None
    if decision not in {"approve", "reject"}:
        return {"error": "decision must be 'approve' or 'reject'."}
    row = store.fetch_submission(_locked_guild_id, code)
    if not row:
        return {"error": f"No submission with code '{code.upper()}'."}
    if row["status"] != "In Queue":
        return {"error": f"This submission was already decided ({row['status']})."}

    new_status = "Approved" if decision == "approve" else "Rejected"
    store.decide_submission(_locked_guild_id, code, new_status, reason=reason)

    # Mirror the staff-card flow: DM the artist and log in the staff thread.
    from core import ui as core_ui

    guild = _bot.get_guild(_locked_guild_id)
    guild_name = guild.name if guild else "the label"
    if new_status == "Approved":
        embed_note = reason or "The team will reach out with next steps."
        embed = _build_embed(
            "Submission Approved 🎉",
            f"Congratulations **{row['artist_name']}** — **{row['track_name']}** was approved by **{guild_name}**!\n\n{embed_note}",
            0x43B581,
            f"Ticket {row['ticket_code']}",
        )
        thread_note = f"✅ Approved via MCP AI assistant.{(' Reason: ' + reason) if reason else ''}"
    else:
        embed = _build_embed(
            "Submission Update",
            (
                f"Hi **{row['artist_name']}**, thanks for sending **{row['track_name']}** to **{guild_name}**.\n\n"
                f"Unfortunately this one isn't the right fit right now.\n\n**Reason:** {reason or 'No specific reason was given.'}"
            ),
            0xF04747,
            f"Ticket {row['ticket_code']}",
        )
        thread_note = f"❌ Rejected via MCP AI assistant. Reason: {reason or 'none given'}"

    dm_sent = _run_coro(core_ui.dm_user(_bot, row["artist_id"], embed))
    _run_coro(core_ui.post_to_thread(_bot, row["staff_thread_id"], thread_note))
    return {
        "ok": True,
        "code": row["ticket_code"],
        "status": new_status,
        "artist_dm_sent": bool(dm_sent),
        "staff_thread_updated": bool(row.get("staff_thread_id")),
    }


def _build_embed(title: str, description: str, color: int, footer: str):
    import discord

    embed = discord.Embed(title=title[:256], description=description[:4000], color=color)
    embed.set_footer(text=footer)
    return embed


def _tool_list_tickets(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    status = str(args.get("status") or "").strip() or None
    if status and status not in TICKET_STATUSES:
        return {"error": f"status must be one of: {', '.join(TICKET_STATUSES)}."}
    try:
        limit = max(1, min(int(args.get("limit") or 15), 50))
    except (TypeError, ValueError):
        limit = 15
    rows = store.list_tickets(_locked_guild_id, status=status, limit=limit)
    return {
        "tickets": [
            {
                "code": r["ticket_code"],
                "username": r.get("username") or "",
                "subject": r["subject"],
                "body": (r.get("body") or "")[:500],
                "status": r["status"],
                "created_at": _iso(r.get("created_at")),
                "updated_at": _iso(r.get("updated_at")),
            }
            for r in rows
        ]
    }


def _tool_set_ticket_status(args: dict) -> dict:
    ready, msg = _bot_ready()
    if not ready:
        return {"error": msg}
    code = str(args.get("code") or "").strip()
    status = str(args.get("status") or "").strip()
    if status not in TICKET_STATUSES:
        return {"error": f"status must be one of: {', '.join(TICKET_STATUSES)}."}
    if not store.set_ticket_status(_locked_guild_id, code, status):
        return {"error": f"No ticket with code '{code.upper()}'."}
    return {"ok": True, "code": code.upper(), "status": status}


# ── tool registry ────────────────────────────────────────────────────────────

_TOOLS = {
    "create_command": _tool_create_command,
    "list_commands": _tool_list_commands,
    "get_command": _tool_get_command,
    "delete_command": _tool_delete_command,
    "set_command_enabled": _tool_set_command_enabled,
    "list_submissions": _tool_list_submissions,
    "get_submission": _tool_get_submission,
    "decide_submission": _tool_decide_submission,
    "list_tickets": _tool_list_tickets,
    "set_ticket_status": _tool_set_ticket_status,
}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


_ACTIONS_NOTE = "Actions: " + ", ".join(ALLOWED_ACTIONS) + ". Member actions (kick/ban/timeout) need a 'user' type parameter; role actions need a role name/ID in input; announce takes a channel ID in input and message in body; webhook_post takes the https URL in input and a JSON payload template in body."

TOOL_SPECS = [
    {
        "name": "create_command",
        "description": (
            "Create or update a custom Discord slash command for this server. " + AUTHORING_POLICY + " " + _ACTIONS_NOTE
        ),
        "inputSchema": _schema(
            {
                "manifest": {
                    "type": "object",
                    "description": (
                        "Command manifest: {name (lowercase_snake_case), description (max 100 chars), "
                        "parameters: [{name, type: string|integer|boolean|user|channel, required?}] (max 5), "
                        "response: {content?, embed?: {title?, description?}}, actions: [{type, input?, body?, store_as?}] "
                        "(1-10), rate_limit: {max_uses_per_user_hour: 1-30 (default 5)}. Placeholders: {param.x} and "
                        "{result.alias.field} in text."
                    ),
                }
            },
            ["manifest"],
        ),
    },
    {
        "name": "list_commands",
        "description": "List every custom command on this server with its enabled state.",
        "inputSchema": _schema({}),
    },
    {
        "name": "get_command",
        "description": "Get the full manifest and usage stats for one custom command.",
        "inputSchema": _schema({"name": {"type": "string", "description": "Command name"}}, ["name"]),
    },
    {
        "name": "delete_command",
        "description": "Permanently delete a custom command.",
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
    },
    {
        "name": "set_command_enabled",
        "description": "Enable or disable a custom command without deleting it.",
        "inputSchema": _schema(
            {"name": {"type": "string"}, "enabled": {"type": "boolean", "description": "true = enable, false = disable"}},
            ["name", "enabled"],
        ),
    },
    {
        "name": "list_submissions",
        "description": "List demo submissions for this server, newest first. status: In Queue, Approved or Rejected.",
        "inputSchema": _schema(
            {
                "status": {"type": "string"},
                "limit": {"type": "integer", "maximum": 50},
            }
        ),
    },
    {
        "name": "get_submission",
        "description": "Get one submission in full by its code (e.g. H7K2M9).",
        "inputSchema": _schema({"code": {"type": "string"}}, ["code"]),
    },
    {
        "name": "decide_submission",
        "description": "Approve or reject a demo submission. The artist is DM'd exactly like a staff member pressing the card buttons, and the staff thread is updated.",
        "inputSchema": _schema(
            {
                "code": {"type": "string", "description": "Submission code (e.g. H7K2M9)"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
                "reason": {"type": "string", "description": "Shown to the artist (especially on reject)"},
            },
            ["code", "decision"],
        ),
    },
    {
        "name": "list_tickets",
        "description": "List support tickets, newest first. status: Open, Waiting, Answered or Resolved.",
        "inputSchema": _schema({"status": {"type": "string"}, "limit": {"type": "integer", "maximum": 50}}),
    },
    {
        "name": "set_ticket_status",
        "description": "Set a support ticket's status.",
        "inputSchema": _schema(
            {"code": {"type": "string"}, "status": {"type": "string", "enum": TICKET_STATUSES}},
            ["code", "status"],
        ),
    },
]


def call_tool(name: str, arguments: dict) -> dict:
    handler = _TOOLS.get(name)
    if not handler:
        return {"error": f"Unknown tool '{name}'.", "available_tools": sorted(_TOOLS)}
    try:
        return handler(arguments or {})
    except Exception as exc:  # surface the failure to the AI, not a 500
        return {"error": f"Tool '{name}' failed: {exc}"}
