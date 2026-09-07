"""Vektra Open - music via a separate Lavalink node (fully optional).

Loads only when LAVALINK_PASSWORD is set in the environment; if the wavelink
package isn't installed the cog is skipped at startup. Do NOT run Lavalink on
the same 150 MB VPS as the bot - point LAVALINK_HOST at another box.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.config import LAVALINK_PASSWORD, MAX_TRACKS_PER_REQUEST
from utils.helpers import format_duration

logger = logging.getLogger("vektra-open.music")

try:
    import wavelink
    WAVELINK_AVAILABLE = True
except ImportError:  # pragma: no cover
    WAVELINK_AVAILABLE = False
    wavelink = None  # type: ignore[assignment]


class MusicCog(commands.Cog, name="Music"):
    """Play music from YouTube - requires the server owner to run a Lavalink node."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── helpers ──────────────────────────────────────────────────────────

    async def _ensure_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return False
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You need to be in a voice channel first.", ephemeral=True)
            return False
        vc = interaction.guild.voice_client
        if vc and vc.channel != interaction.user.voice.channel:
            await interaction.response.send_message("I'm already in a different voice channel.", ephemeral=True)
            return False
        return True

    async def _join_voice(self, interaction: discord.Interaction) -> "wavelink.Player | None":
        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if isinstance(vc, wavelink.Player):
            if vc.channel != channel:
                try:
                    await vc.move_to(channel)
                except Exception:
                    logger.exception("Failed to move music player.")
                    return None
            return vc
        try:
            player: wavelink.Player = await channel.connect(cls=wavelink.Player, self_deaf=True)
            return player
        except Exception:
            logger.exception("Failed to join voice.")
            await interaction.followup.send("❌ Could not join your voice channel.", ephemeral=True)
            return None

    async def _search_tracks(self, query: str) -> list:
        attempts = [query, f"ytsearch:{query}", f"ytmsearch:{query}"]
        last_error: Exception | None = None
        for attempt in attempts:
            try:
                results = await wavelink.Playable.search(attempt)
                tracks = list(results.tracks) if hasattr(results, "tracks") else list(results)
                if tracks:
                    return tracks
            except Exception as exc:
                last_error = exc
                logger.warning("Wavelink search failed for %r: %s", attempt, exc)
        if last_error:
            raise last_error
        return []

    def _node_ready(self) -> bool:
        return bool(wavelink is not None and wavelink.Pool.nodes)

    # ── events ───────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload) -> None:
        player: "wavelink.Player" = payload.player
        track = payload.track
        home = getattr(player, "home", None)
        if home is None or track is None:
            return
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{track.title}]({getattr(track, 'uri', '')})**",
            color=0x9B59B6,
        )
        embed.add_field(name="Duration", value=format_duration(track.duration // 1000 if track.duration else 0))
        try:
            await home.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload) -> None:
        player: "wavelink.Player" = payload.player
        if len(player.queue) == 0:
            return
        next_track = player.queue.get()
        await player.play(next_track)

    # ── commands ─────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song or search YouTube")
    @app_commands.describe(query="YouTube URL or search query")
    async def play(self, interaction: discord.Interaction, query: str):
        if not WAVELINK_AVAILABLE:
            await interaction.response.send_message("Music is disabled (wavelink is not installed).", ephemeral=True)
            return
        if not LAVALINK_PASSWORD:
            await interaction.response.send_message(
                "Music is disabled - the server owner has not configured a Lavalink node.",
                ephemeral=True,
            )
            return
        if not self._node_ready():
            await interaction.response.send_message(
                "Lavalink is not connected yet. Try again in a few seconds.",
                ephemeral=True,
            )
            return
        if not await self._ensure_voice(interaction):
            return
        await interaction.response.defer(thinking=True)
        vc = await self._join_voice(interaction)
        if vc is None:
            return
        try:
            tracks = await self._search_tracks(query)
        except Exception:
            await interaction.followup.send("❌ Couldn't find or load that track.", ephemeral=True)
            return
        if not tracks:
            await interaction.followup.send("❌ No results for that query.", ephemeral=True)
            return
        tracks = tracks[:MAX_TRACKS_PER_REQUEST]
        vc.home = interaction.channel
        starting = vc.current is None
        for track in tracks:
            vc.queue.put(track)
        if starting:
            await vc.play(vc.queue.get())
        if len(tracks) == 1:
            await interaction.followup.send(f"✅ Added to queue: **{tracks[0].title}**")
        else:
            await interaction.followup.send(f"✅ Added **{len(tracks)}** tracks to the queue.")

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(vc, wavelink.Player) or vc.current is None:
            await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
            return
        if len(vc.queue) == 0:
            await vc.stop()
            await interaction.response.send_message("⏹ Stopped playback.")
            return
        await vc.skip(force=True)
        await interaction.response.send_message("⏭ Skipped.")

    @app_commands.command(name="stop", description="Stop playback and leave the voice channel")
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        try:
            await vc.disconnect()
        except Exception:
            logger.exception("Failed to disconnect music player.")
        await interaction.response.send_message("⏹ Stopped and disconnected.")

    @app_commands.command(name="pause", description="Pause or resume playback")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(vc, wavelink.Player):
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if vc.paused:
            await vc.pause(False)
            await interaction.response.send_message("▶ Resumed.")
        elif vc.playing:
            await vc.pause(True)
            await interaction.response.send_message("⏸ Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="music_queue", description="Show the current music queue")
    async def music_queue(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(vc, wavelink.Player) or (vc.current is None and len(vc.queue) == 0):
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        embed = discord.Embed(title="🎵 Music Queue", color=0x9B59B6)
        if vc.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{vc.current.title}** [{format_duration(vc.current.duration // 1000 if vc.current.duration else 0)}]",
                inline=False,
            )
        lines = []
        for index, track in enumerate(list(vc.queue)[:10], start=1):
            lines.append(f"`{index}.` **{track.title}** [{format_duration(track.duration // 1000 if track.duration else 0)}]")
        if len(vc.queue) > 10:
            lines.append(f"*…and {len(vc.queue) - 10} more*")
        if lines:
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    async def nowplaying(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(vc, wavelink.Player) or vc.current is None:
            await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
            return
        track = vc.current
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{track.title}]({getattr(track, 'uri', '')})**",
            color=0x9B59B6,
        )
        embed.add_field(name="Duration", value=format_duration(track.duration // 1000 if track.duration else 0))
        embed.add_field(name="In Queue", value=str(len(vc.queue)))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set playback volume (1-100)")
    @app_commands.describe(level="Volume level from 1 to 100")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 100]):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(vc, wavelink.Player):
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await vc.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @app_commands.command(name="leave", description="Disconnect the bot from voice")
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not vc:
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        try:
            await vc.disconnect()
        except Exception:
            logger.exception("Failed to disconnect music player.")
        await interaction.response.send_message("👋 Disconnected.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
