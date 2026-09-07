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

from core import database as store
from core import ui
from core.config import (
    CHECKOUT_RECEIPT_SECRET,
    DATABASE_URL,
    DEFAULT_PRESENCE_TEXT,
    DISCORD_BOT_TOKEN,
    HEALTH_HOST,
    LAVALINK_HOST,
    LAVALINK_IDENTIFIER,
    LAVALINK_PASSWORD,
    LAVALINK_PORT,
    LAVALINK_SSL,
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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/health"}:
            self._send(b"Vektra Open Discord bot is running.\n")
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
        for cog in ("cogs.admin", "cogs.submissions", "cogs.tickets", "cogs.music"):
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

        if LAVALINK_PASSWORD:
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
                    logger.warning("Timed out connecting Lavalink node at %s.", node_uri)
                except Exception:
                    logger.exception("Failed to connect Lavalink node at %s.", node_uri)
        else:
            logger.info("LAVALINK_PASSWORD not set - music commands will report disabled.")

        command_names = ", ".join(command.name for command in self.tree.get_commands())
        logger.info("Registering global slash commands: %s", command_names)
        synced = await self.tree.sync()
        logger.info("Synced %s global slash commands.", len(synced))


bot = VektraBot()


@bot.event
async def on_ready():
    logger.info("Vektra Open is online as %s in %s guild(s).", bot.user, len(bot.guilds))
    activity = discord.Activity(type=discord.ActivityType.listening, name=DEFAULT_PRESENCE_TEXT)
    try:
        await bot.change_presence(activity=activity)
    except discord.HTTPException:
        logger.warning("Could not update presence.")


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
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception:
        logger.exception("Unhandled exception during startup or runtime.")
        sys.exit(1)
