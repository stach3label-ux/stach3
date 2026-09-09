#!/usr/bin/env python3
"""Vektra Open - the open-source, free-tier Vektra Discord bot.

Single process: Discord bot + a tiny built-in HTTP server. Runs happily on a
~150 MB VPS and talks to any Postgres you already have (Neon, Supabase, or a
self-hosted box) through one DATABASE_URL.

Quick start:
    cp .env.example .env          # fill in DISCORD_BOT_TOKEN + DATABASE_URL
    python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import discord
from discord import app_commands
from discord.ext import commands

from mcp import http_api as mcp_http

from core import database as store
from core import single_server, ui
from core.config import (
    CHECKOUT_RECEIPT_SECRET,
    DATABASE_URL,
    DEFAULT_PRESENCE_TEXT,
    DISCORD_BOT_TOKEN,
    GUILD_ID,
    HEALTH_HOST,
    LAVALINK_HOST,
    LAVALINK_IDENTIFIER,
    LAVALINK_PASSWORD,
    LAVALINK_PORT,
    LAVALINK_SSL,
    MCP_PASSWORD,
    MUSIC_ENABLED,
    PORT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vektra-open")

intents = discord.Intents.default()
intents.message_content = True


# ── HTTP server ──────────────────────────────────────────────────────────────

class HealthRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.debug("http: " + fmt, *args)

    def _send(self, body: bytes, status: int = 200, content_type: str = "text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _form(self) -> dict:
        """Parse an application/x-www-form-urlencoded body (OAuth posts)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1_000_000)).decode("utf-8", "replace")
        try:
            return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        except ValueError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/health"}:
            self._send(b"Vektra Open Discord bot is running.\n")
            return

        # ── AI MCP server (OAuth connector flow + JSON-RPC endpoint) ──
        if path == "/.well-known/oauth-authorization-server":
            mcp_http.handle_mcp_well_known(self)
            return
        if path == "/oauth/authorize":
            mcp_http.handle_authorize_get(self, {k: v[0] for k, v in parse_qs(parsed.query).items()})
            return
        if path == "/mcp":
            mcp_http.handle_mcp_get(self)
            return

        if path == "/callback":
            # Completion callback stub (offerwall-style). Replace the body with
            # your own fulfilment logic - it currently just acknowledges.
            self._send(b"1\n")
            return

        if path == "/receipt":
            # Receipt endpoint stub. A checkout site can call
            #   GET /receipt?order_ref=...&secret=...
            # to trigger a receipt DM. This open version logs the call; wire in
            # your own order lookup + DM logic here.
            qs = parse_qs(parsed.query)
            order_ref = (qs.get("order_ref") or [None])[0]
            secret = (qs.get("secret") or [None])[0]
            if CHECKOUT_RECEIPT_SECRET and secret != CHECKOUT_RECEIPT_SECRET:
                self._send(b"Forbidden: Invalid secret.\n", status=403)
                return
            if not order_ref:
                self._send(b"Bad Request: Missing order_ref parameter.\n", status=400)
                return
            logger.info("Receipt requested for order_ref=%s (stub).", order_ref)
            self._send(b"1\n")
            return

        self._send(b"Not Found\n", status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── AI MCP server ─────────────────────────────────────────────
        if path == "/oauth/authorize":
            mcp_http.handle_authorize_post(self, self._form())
            return
        if path == "/oauth/token":
            mcp_http.handle_token_post(self, self._form())
            return
        if path == "/oauth/revoke":
            mcp_http.handle_revoke_post(self, self._form())
            return
        if path == "/mcp":
            mcp_http.handle_mcp_post(self)
            return

        self._send(b"Not Found\n", status=404)


def start_http_server() -> None:
    try:
        server = ThreadingHTTPServer((HEALTH_HOST, PORT), HealthRequestHandler)
    except OSError as exc:
        if exc.errno in {98, 48}:
            logger.warning("HTTP server already in use on %s:%s; continuing without it.", HEALTH_HOST, PORT)
            return
        logger.exception("Could not start HTTP server on %s:%s.", HEALTH_HOST, PORT)
        return
    thread = Thread(target=server.serve_forever, name="http-server", daemon=True)
    thread.start()
    logger.info("HTTP server listening on http://%s:%s", HEALTH_HOST, PORT)


# ── bot ──────────────────────────────────────────────────────────────────────

class VektraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        cogs = ["cogs.admin", "cogs.submissions", "cogs.tickets"]
        # MUSIC_ENABLED=False keeps music commands from ever registering and
        # leaves Lavalink alone entirely.
        if MUSIC_ENABLED:
            cogs.append("cogs.music")
        else:
            logger.info("MUSIC_ENABLED is false - skipping music commands entirely.")
        # Custom commands (authored via the AI MCP) - only useful when the MCP
        # server is on, but harmless otherwise (the table just stays empty).
        cogs.append("cogs.custom_commands")
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info("Loaded extension %s", cog)
            except Exception:
                logger.exception("Failed to load extension %s", cog)

        # Persistent views - must be re-registered on every start.
        self.add_view(ui.SubmissionDecisionView())
        self.add_view(ui.TicketStaffView())
        self.add_view(ui.SubmitPanelView())
        self.add_view(ui.SupportTicketPanelView())

        if MUSIC_ENABLED:
            if not LAVALINK_PASSWORD:
                logger.warning("MUSIC_ENABLED is true but Lavalink is not configured (LAVALINK_PASSWORD missing). Music commands will report 'Lavalink is not configured'.")
            else:
                try:
                    import wavelink
                except ImportError:
                    logger.warning("LAVALINK_PASSWORD is set but wavelink is not installed; music disabled.")
                else:
                    node_uri = f"{'https' if LAVALINK_SSL else 'http'}://{LAVALINK_HOST}:{LAVALINK_PORT}"
                    try:
                        await asyncio.wait_for(
                            wavelink.Pool.connect(
                                nodes=[wavelink.Node(identifier=LAVALINK_IDENTIFIER, uri=node_uri, password=LAVALINK_PASSWORD)],
                                client=self,
                            ),
                            timeout=15,
                        )
                        logger.info("Connected Lavalink node %s at %s.", LAVALINK_IDENTIFIER, node_uri)
                    except asyncio.TimeoutError:
                        logger.warning("Timed out connecting Lavalink node at %s; music commands will report 'Lavalink is not configured'.", node_uri)
                    except Exception:
                        logger.exception("Failed to connect Lavalink node at %s.", node_uri)
        else:
            logger.info("MUSIC_ENABLED is false - Lavalink is not being used.")

        command_names = ", ".join(command.name for command in self.tree.get_commands())
        logger.info("Registering global slash commands: %s", command_names)
        synced = await self.tree.sync()
        logger.info("Synced %s global slash commands.", len(synced))


bot = VektraBot()


@bot.event
async def on_ready():
    logger.info("Vektra Open is online as %s in %s guild(s).", bot.user, len(bot.guilds))

    # Single-server lock: bind to the configured/first server and leave any others.
    locked = await single_server.claim_first_guild(bot, store, GUILD_ID)
    from mcp import tools as mcp_tools
    mcp_tools.bind_bot(bot)
    mcp_tools.set_locked_guild(locked)

    activity = discord.Activity(type=discord.ActivityType.listening, name=DEFAULT_PRESENCE_TEXT)
    try:
        await bot.change_presence(activity=activity)
    except discord.HTTPException:
        logger.warning("Could not update presence.")


@bot.event
async def on_guild_join(guild: discord.Guild):
    locked_raw = store.get_state(single_server.LOCK_KEY)
    try:
        locked = int(locked_raw or 0) or int(GUILD_ID or 0)
    except (TypeError, ValueError):
        locked = int(GUILD_ID or 0)
    if not locked:
        # First server to invite the bot claims the lock.
        store.set_state(single_server.LOCK_KEY, str(guild.id))
        logger.info("Single-server mode: bound to %s (%s).", guild.name, guild.id)
        locked = guild.id
    elif guild.id != locked:
        logger.warning(
            "Single-server mode: leaving guild %s (%s) - this bot is bound to server %s.",
            guild.name,
            guild.id,
            locked,
        )
        try:
            await guild.leave()
        except Exception:
            logger.exception("Failed to leave guild %s.", guild.id)


@bot.event
async def on_message(message: discord.Message):
    # DM bridge: when a member DMs the bot, forward it into their most recent
    # open support-ticket thread so staff can answer from the staff channel.
    if message.guild is None and not message.author.bot:
        ticket = store.open_ticket_for_dm(message.author.id)
        if ticket and ticket.get("thread_id"):
            thread = bot.get_channel(ticket["thread_id"])
            if thread is not None:
                text = message.content.strip()
                attachment = message.attachments[0].url if message.attachments else ""
                if text or attachment:
                    payload = f"📩 **{message.author}** (DM): "
                    payload += text if text else attachment
                    if text and attachment:
                        payload += f"\n{attachment}"
                    try:
                        await thread.send(payload)
                        return
                    except discord.HTTPException:
                        logger.warning("Could not forward DM to ticket thread %s.", ticket["thread_id"])


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(
        "Slash command %s failed: %s",
        getattr(getattr(interaction, "command", None), "name", "unknown"),
        error,
    )
    text = "That command failed inside the bot. Check the host logs for details."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        logger.warning("Could not send error reply (interaction expired?).")


# ── entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set. Aborting.")
        sys.exit(1)
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not set - the bot will run but nothing can be stored.")

    try:
        store.ensure_schema()
    except Exception:
        logger.exception("Database schema setup failed - check DATABASE_URL and connectivity.")

    start_http_server()
    if MCP_PASSWORD:
        logger.info("AI MCP server enabled: connect assistants to http://<this-host>:%s/mcp (password auth).", PORT)
    else:
        logger.info("MCP_PASSWORD is not set - the AI MCP server is disabled.")
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception:
        logger.exception("Unhandled exception during startup or runtime.")
        sys.exit(1)
