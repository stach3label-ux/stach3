"""
Vektra Open - single-server lock.

The open-source edition is meant for one label and one server. The first
server the bot joins becomes its permanent home (stored in the bot_state
table); every other server it is invited to is left automatically. Set
GUILD_ID in the environment to pin a specific server instead.

This file is intentionally small and self-contained: anyone who wants to
run the bot commercially / multi-server is expected to fork and replace it.
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger("vektra-open.single-server")

LOCK_KEY = "locked_guild_id"


def resolve_locked_guild_id(store, config_guild_id: int) -> int:
    """Return the guild id this bot is bound to, creating the binding if needed.

    Priority: the explicit GUILD_ID env var, then the stored binding from the
    first server that ever invited the bot. Returns 0 when nothing is bound
    yet (the next guild to join will claim the lock).
    """
    if config_guild_id:
        stored = store.get_state(LOCK_KEY)
        if stored and int(stored) != config_guild_id:
            logger.warning(
                "GUILD_ID env var overrides the previously locked server %s with %s.",
                stored,
                config_guild_id,
            )
        store.set_state(LOCK_KEY, str(config_guild_id))
        return config_guild_id

    stored = store.get_state(LOCK_KEY)
    if stored:
        try:
            return int(stored)
        except (TypeError, ValueError):
            logger.warning("Corrupt locked_guild_id value %r; ignoring.", stored)
            return 0
    return 0


async def enforce(bot: discord.Client, store, locked_guild_id: int, *, guild_ids: set[int] | None = None) -> None:
    """Leave any guild that is not the locked one.

    Call from on_ready (with the bot's current guilds) and on_guild_join
    (with the single new guild). With no lock established yet, the first
    guild to join claims it - that is handled by the caller via
    resolve_locked_guild_id / claim_first_guild.
    """
    if not locked_guild_id:
        return
    targets = guild_ids if guild_ids is not None else {g.id for g in bot.guilds}
    for gid in targets:
        if gid != locked_guild_id:
            guild = bot.get_guild(gid)
            logger.warning(
                "Single-server mode: leaving guild %s (%s) - this bot is bound to server %s.",
                gid,
                getattr(guild, "name", "unknown"),
                locked_guild_id,
            )
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave guild %s.", gid)


async def claim_first_guild(bot: discord.Client, store, config_guild_id: int) -> int:
    """Bind the bot to GUILD_ID (if set) or the first guild it is in.

    Returns the resolved lock id (0 when the bot is in no guild yet).
    """
    locked = resolve_locked_guild_id(store, config_guild_id)
    if locked:
        await enforce(bot, store, locked)
        return locked

    if bot.guilds:
        first = bot.guilds[0]
        store.set_state(LOCK_KEY, str(first.id))
        logger.info(
            "Single-server mode: bound to %s (%s). Other servers will be left automatically.",
            first.name,
            first.id,
        )
        await enforce(bot, store, first.id)
        return first.id

    logger.info(
        "Single-server mode: no server yet. The first server that invites this bot becomes its permanent home."
    )
    return 0
