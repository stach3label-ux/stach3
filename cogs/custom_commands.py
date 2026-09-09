"""Vektra Open - custom commands authored through the AI MCP.

Commands are declarative JSON manifests (never code) created via the MCP
endpoint. This cog polls the custom_commands table, registers them as
guild-scoped slash commands, and interprets their whitelisted actions inside
a strict sandbox - no arbitrary code ever runs.

There is no approval step here (that is the point of the AI MCP): the AI
assistant itself decides what is acceptable, and every action that touches
a Discord member is permission-checked at RUNTIME against whoever invoked
the command. The bot never elevates anyone.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core import database as store

logger = logging.getLogger("vektra-open.custom-commands")

POLL_SECONDS = 60
MAX_PARAMS = 5
MAX_ACTIONS = 10

_PARAM_TYPES = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "user": discord.Member,
    "channel": discord.TextChannel,
}


def _render(template: str, ctx: dict) -> str:
    """Substitute {param.x} / {result.alias.field} placeholders."""

    def repl(match: re.Match) -> str:
        key = match.group(1)
        value = ctx.get(key)
        if value is None:
            return ""
        return str(value)

    return re.sub(r"\{([a-z0-9_.]+)\}", repl, str(template or ""))


class CustomCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._fingerprint: str = ""
        self._registered: dict[int, set[str]] = {}
        self._poll_task: asyncio.Task | None = None
        # The MCP tools set this to re-sync within seconds of a change.
        self.refresh_event = asyncio.Event()
        bot.custom_commands_refresh = self.refresh_event

    async def cog_load(self):
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def cog_unload(self):
        if self._poll_task:
            self._poll_task.cancel()

    # ── registration sync ───────────────────────────────────────────

    async def _poll_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.refresh_registrations()
            except Exception:
                logger.exception("Custom command refresh failed.")
            try:
                await asyncio.wait_for(self.refresh_event.wait(), timeout=POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            self.refresh_event.clear()

    async def refresh_registrations(self):
        rows = await asyncio.to_thread(store.list_enabled_custom_commands)

        by_guild: dict[int, list[dict]] = {}
        fingerprint_parts: list[str] = []
        for row in rows:
            gid = int(row["guild_id"])
            manifest = row["manifest"] if isinstance(row["manifest"], dict) else json.loads(row["manifest"])
            by_guild.setdefault(gid, []).append({"name": row["name"], "manifest": manifest})
            fingerprint_parts.append(f"{gid}:{row['name']}:{row.get('updated_at')}")

        # Single-server bot: only the locked guild gets commands.
        from core.config import GUILD_ID
        from core.single_server import LOCK_KEY

        locked_raw = await asyncio.to_thread(store.get_state, LOCK_KEY)
        try:
            locked = int(locked_raw or 0) or int(GUILD_ID or 0)
        except (TypeError, ValueError):
            locked = int(GUILD_ID or 0)

        eligible: dict[int, list[dict]] = {}
        if locked and locked in by_guild and self.bot.get_guild(locked):
            eligible[locked] = by_guild[locked]

        new_fingerprint = "|".join(sorted(fingerprint_parts))
        needs_sync = new_fingerprint != self._fingerprint

        for gid, cmds in eligible.items():
            obj = discord.Object(id=gid)
            wanted = {c["name"] for c in cmds}
            registered = self._registered.get(gid, set())

            for stale in registered - wanted:
                try:
                    self.bot.tree.remove_command(stale, guild=obj)
                    needs_sync = True
                except Exception:
                    logger.exception("Failed to remove custom command /%s.", stale)

            for entry in cmds:
                try:
                    already_present = self.bot.tree.get_command(entry["name"], guild=obj) is not None
                    command = self._build_command(entry)
                    self.bot.tree.add_command(command, guild=obj, override=True)
                    if not already_present:
                        needs_sync = True
                except Exception:
                    logger.exception("Failed to register custom command /%s.", entry["name"])

            self._registered[gid] = wanted

        # Deregister anything that no longer applies (disabled / deleted / guild left).
        for gid in list(self._registered.keys()):
            if gid not in eligible:
                obj = discord.Object(id=gid)
                for name in self._registered.pop(gid):
                    try:
                        self.bot.tree.remove_command(name, guild=obj)
                        needs_sync = True
                    except Exception:
                        pass

        if needs_sync and eligible:
            try:
                await self.bot.tree.sync(guild=discord.Object(id=locked))
                logger.info("Synced custom commands to guild %s.", locked)
            except Exception:
                logger.exception("Failed to sync custom commands to guild %s.", locked)
        self._fingerprint = new_fingerprint

    # ── command factory ─────────────────────────────────────────────

    def _build_command(self, entry: dict) -> app_commands.Command:
        manifest = entry["manifest"]
        params = [p for p in (manifest.get("parameters") or [])[:MAX_PARAMS] if p.get("name")]

        signature = "interaction"
        call_args = []
        annotations = {}
        namespace = {"discord": discord}
        for p in params:
            pname = str(p["name"])
            py_type = _PARAM_TYPES.get(str(p.get("type", "string")), str)
            annotations[pname] = py_type
            signature += f", {pname}={json.dumps(None)}"
            call_args.append(f"'{pname}': {pname}")
        namespace.update(annotations)

        src = (
            f"async def _dynamic({signature}):\n"
            f"    await __dispatcher(interaction, {{{', '.join(call_args)}}})\n"
        )
        namespace["__dispatcher"] = lambda interaction, kwargs: self.run_manifest(manifest, interaction, kwargs)
        exec(compile(src, "<custom-command>", "exec"), namespace)
        callback = namespace["_dynamic"]
        callback.__annotations__ = {"interaction": discord.Interaction, **annotations}

        return app_commands.Command(
            name=str(entry["name"]),
            description=str(manifest.get("description") or "Custom command")[:100],
            callback=callback,
        )

    # ── interpreter ─────────────────────────────────────────────────

    def _resolve_role(self, guild: discord.Guild, identifier: str) -> discord.Role | None:
        ident = str(identifier).strip().strip("<@&>")
        if ident.isdigit():
            role = guild.get_role(int(ident))
            if role:
                return role
        needle = ident.lower()
        for role in guild.roles:
            if role.name.lower() == needle:
                return role
        return None

    def _resolve_target(self, interaction, kwargs) -> discord.Member | None:
        user_param = kwargs.get("user")
        if isinstance(user_param, discord.Member):
            return user_param
        return interaction.user

    def _caller_perms(self, interaction) -> discord.Permissions | None:
        return interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None

    async def _run_member_action(self, command_name, action_type, interaction, member, reason):
        """Moderation actions - the CALLER must hold the matching Discord
        permission; the bot never elevates anyone."""
        perms = self._caller_perms(interaction)
        required = {
            "kick_member": ("kick_members", "kick"),
            "ban_member": ("ban_members", "ban"),
            "timeout_member": ("moderate_members", "timeout"),
        }.get(action_type)
        if not required or perms is None or not getattr(perms, required[0]):
            await interaction.followup.send("You do not have permission to do that.", ephemeral=True)
            return {"done": "no", "error": "missing caller permission"}

        bot_perms = interaction.app_permissions
        if not getattr(bot_perms, {"kick": "kick_members", "ban": "ban_members", "timeout": "moderate_members"}[required[1]]):
            await interaction.followup.send("I do not have permission to do that here.", ephemeral=True)
            return {"done": "no", "error": "missing bot permission"}
        if (
            isinstance(interaction.user, discord.Member)
            and member.top_role >= interaction.user.top_role
            and interaction.guild.owner_id != interaction.user.id
        ):
            await interaction.followup.send("You cannot moderate someone with an equal or higher role than you.", ephemeral=True)
            return {"done": "no", "error": "hierarchy"}

        audit_reason = f"/{command_name} by {interaction.user} - {reason}"[:450]
        try:
            if action_type == "kick_member":
                await member.kick(reason=audit_reason)
                return {"done": "yes", "member": str(member)}
            if action_type == "ban_member":
                await interaction.guild.ban(member, reason=audit_reason)
                return {"done": "yes", "member": str(member)}
            if action_type == "timeout_member":
                minutes = int(str(reason).strip().split()[0]) if str(reason).strip().split() else 10
                minutes = max(1, min(minutes, 40320))
                until = discord.utils.utcnow() + timedelta(minutes=minutes)
                await member.timeout(until, reason=audit_reason)
                return {"done": "yes", "member": str(member), "minutes": minutes}
        except discord.Forbidden:
            return {"done": "no", "error": "forbidden (check role hierarchy)"}
        except Exception as exc:
            logger.exception("Member action failed.")
            return {"done": "no", "error": str(exc)[:200]}
        return {"done": "no", "error": "unknown action"}

    def _apply_role_action(self, interaction, action_type: str, role_identifier: str, member):
        role = self._resolve_role(interaction.guild, role_identifier)
        if not role:
            return {"done": "no", "error": f"role '{role_identifier}' not found"}
        bot_member = interaction.guild.get_member(self.bot.user.id)
        if not bot_member or bot_member.top_role <= role:
            return {"done": "no", "error": "my highest role must be above that role"}
        perms = self._caller_perms(interaction)
        if member != interaction.user and (not perms or not perms.manage_roles):
            return {"done": "no", "error": "you need Manage Roles to target other members"}
        reason = f"Custom command by {interaction.user}"
        try:
            if action_type == "give_role":
                coro = member.add_roles(role, reason=reason)
            else:
                coro = member.remove_roles(role, reason=reason)
        except discord.Forbidden:
            return {"done": "no", "error": "forbidden"}
        return {"role": role.name}

    async def _webhook_post(self, url: str, body_template: str, ctx: dict):
        body_text = _render(body_template or "{}", ctx).strip()
        try:
            payload_body = json.loads(body_text) if body_text else {}
        except ValueError:
            return {"status": 0, "error": "body is not valid JSON"}
        try:
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(payload_body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read(2000).decode("utf-8", "replace")
                return {"status": resp.status, "response": text}
        except Exception as exc:
            return {"status": 0, "error": str(exc)[:200]}

    async def run_manifest(self, manifest: dict, interaction: discord.Interaction, kwargs: dict):
        guild_id = interaction.guild_id
        name = str(manifest.get("name") or "")
        rate_limit = manifest.get("rate_limit") or {}
        try:
            max_per_hour = int(rate_limit.get("max_uses_per_user_hour", 5))
        except (TypeError, ValueError):
            max_per_hour = 5

        allowed = await asyncio.to_thread(
            store.check_and_record_command_usage, guild_id, name, interaction.user.id, max_per_hour
        )
        if not allowed:
            await interaction.response.send_message(
                "You have used this command a lot recently - please try again later.",
                ephemeral=True,
            )
            return

        ctx: dict[str, object] = {f"param.{k}": v for k, v in kwargs.items()}
        results: dict[str, object] = {}

        try:
            for index, action in enumerate((manifest.get("actions") or [])[:MAX_ACTIONS]):
                action_type = str(action.get("type", ""))
                alias = str(action.get("store_as") or action_type) or f"action{index}"
                raw_input = _render(action.get("input", ""), ctx)

                value: object = None
                if action_type == "text_reply":
                    value = {"text": str(raw_input)}
                elif action_type == "random_pick":
                    options = [opt.strip() for opt in str(raw_input).split("|") if opt.strip()]
                    value = {"pick": random.choice(options) if options else ""}
                elif action_type == "show_link":
                    value = {"link": str(raw_input)}
                elif action_type == "lookup_submission":
                    value = await asyncio.to_thread(self._lookup_submission, guild_id, str(raw_input).strip()) or {"found": "no"}
                elif action_type == "my_submissions":
                    subs = await asyncio.to_thread(self._my_submissions, guild_id, interaction.user.id)
                    value = {
                        "count": len(subs),
                        "lines": "\n".join(
                            f"`{s['ticket_code']}` {s['track_name']} - {s['status']}" for s in subs
                        ) or "No submissions yet.",
                    }
                elif action_type in ("give_role", "remove_role"):
                    member = self._resolve_target(interaction, kwargs)
                    value = self._apply_role_action(interaction, action_type, raw_input, member)
                elif action_type in ("kick_member", "ban_member", "timeout_member"):
                    member = self._resolve_target(interaction, kwargs)
                    value = await self._run_member_action(
                        name,
                        action_type,
                        interaction,
                        member,
                        _render(action.get("body", "") or raw_input, ctx) or "Custom command",
                    )
                elif action_type == "announce":
                    channel_id = int(re.sub(r"\D", "", str(raw_input)) or 0)
                    channel = interaction.guild.get_channel(channel_id) if channel_id else None
                    text = _render(action.get("body", ""), ctx).strip()
                    if not channel or not isinstance(channel, discord.TextChannel):
                        value = {"sent": "no", "error": "channel not found"}
                    elif not channel.permissions_for(interaction.guild.me).send_messages:
                        value = {"sent": "no", "error": "I cannot send messages there"}
                    else:
                        await channel.send(text[:2000] or "(empty)")
                        value = {"sent": "yes", "channel": str(raw_input)}
                elif action_type == "webhook_post":
                    url = str(raw_input).strip()
                    if not url.startswith(("http://", "https://")):
                        value = {"status": 0, "error": "invalid URL"}
                    else:
                        value = await self._webhook_post(url, action.get("body", ""), ctx)
                # Unknown action types are ignored.

                results[alias] = value
                if isinstance(value, dict):
                    for field, field_value in value.items():
                        ctx[f"result.{alias}.{field}"] = field_value
                    ctx[f"result.{alias}"] = next(iter(value.values()), "")
                else:
                    ctx[f"result.{alias}"] = value
        except Exception:
            logger.exception("Custom command /%s failed.", name)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "This command hit an error.",
                    ephemeral=True,
                )
            return

        response = manifest.get("response") or {}
        content = _render(response.get("content"), ctx).strip()
        embed = None
        embed_data = response.get("embed")
        if isinstance(embed_data, dict):
            title = _render(embed_data.get("title"), ctx).strip()
            description = _render(embed_data.get("description"), ctx).strip()
            if title or description:
                embed = discord.Embed(title=title[:256] or None, description=description[:4000] or None)

        message_kwargs = {"ephemeral": bool(response.get("ephemeral", True))}
        if content:
            message_kwargs["content"] = content[:2000]
        if embed:
            message_kwargs["embed"] = embed
        if not content and not embed:
            message_kwargs["content"] = "Done."

        if not interaction.response.is_done():
            await interaction.response.send_message(**message_kwargs)

    # ── submission lookups ──────────────────────────────────────────

    def _lookup_submission(self, guild_id: int, code: str) -> dict | None:
        row = store.fetch_submission(guild_id, code)
        if not row:
            return None
        return {
            "found": "yes",
            "code": row["ticket_code"],
            "track_name": row["track_name"],
            "artist_name": row["artist_name"],
            "status": row["status"],
        }

    def _my_submissions(self, guild_id: int, user_id: int) -> list[dict]:
        rows = store.list_submissions(guild_id, artist_id=user_id, limit=5)
        return [
            {
                "ticket_code": r["ticket_code"],
                "track_name": r["track_name"],
                "status": r["status"],
                "created": r["created_at"].strftime("%Y-%m-%d") if r.get("created_at") else "",
            }
            for r in rows
        ]


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommandsCog(bot))
