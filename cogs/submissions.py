"""Vektra Open - demo intake and submission browsing commands."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import database as store
from core import ui
from core.config import COLOR_BLURPLE, COLOR_GREEN
from utils.helpers import parse_ticket_code

logger = logging.getLogger("vektra-open.submissions")


class SubmissionsCog(commands.Cog, name="Submissions"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── artists ──────────────────────────────────────────────────────────

    @app_commands.command(name="submit", description="Submit your demo to the label")
    async def submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Run `/submit` inside the label's server.", ephemeral=True)
            return
        await interaction.response.send_modal(ui.SubmissionModal())

    @app_commands.command(name="my_submissions", description="Show the demos you submitted in this server")
    async def my_submissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = store.list_submissions(
            interaction.guild_id,
            artist_id=interaction.user.id,
            limit=10,
        )
        embed = ui.my_submissions_embed(rows, interaction.guild.name)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="my_stats", description="Show your acceptance stats in this server")
    async def my_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        stats = store.artist_stats(interaction.guild_id, interaction.user.id)
        embed = discord.Embed(title="My Demo Stats", color=COLOR_GREEN)
        embed.add_field(name="Submitted", value=str(stats["total"]), inline=True)
        embed.add_field(name="Approved", value=str(stats["approved"]), inline=True)
        embed.add_field(name="In Queue", value=str(stats["in_queue"]), inline=True)
        embed.add_field(name="Rejected", value=str(stats["rejected"]), inline=True)
        if stats["total"]:
            rate = round(stats["approved"] / stats["total"] * 100, 1)
            embed.add_field(name="Acceptance Rate", value=f"{rate}%", inline=True)
        else:
            embed.description = "You have not submitted any demos in this server yet."
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── staff browsing ────────────────────────────────────────────────────

    @app_commands.command(name="queue", description="Staff: show the newest queued submissions")
    async def queue(self, interaction: discord.Interaction):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        rows = store.list_submissions(interaction.guild_id, status="In Queue", limit=5)
        embed = ui.submission_list_embed(rows, "Newest Queued Submissions")
        embed.description = "Decide from the staff channel cards, or view one with `/submission <ticket>`."
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="recent", description="Staff: show the newest submissions in any state")
    async def recent(self, interaction: discord.Interaction):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        rows = store.list_submissions(interaction.guild_id, limit=10)
        embed = ui.submission_list_embed(rows, "Newest Submissions")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="submission", description="Staff: full detail for one submission")
    @app_commands.describe(ticket="Submission ticket code, e.g. H7K2M9")
    async def submission_detail(self, interaction: discord.Interaction, ticket: str):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        code = parse_ticket_code(ticket)
        row = store.fetch_submission(interaction.guild_id, code)
        if not row:
            await interaction.response.send_message(f"No submission found for `{code}`.", ephemeral=True)
            return
        embed = ui.submission_detail_embed(row, interaction.guild.name)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── panels ────────────────────────────────────────────────────────────

    @app_commands.command(name="post_submit_panel", description="Admin: post a public 'Submit a Demo' button panel")
    @app_commands.describe(channel="Channel where artists click the button")
    async def post_submit_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title=f"Submit to {interaction.guild.name}",
            description="Click the button below to send your demo to the A&R team.",
            color=COLOR_BLURPLE,
        )
        try:
            await channel.send(embed=embed, view=ui.SubmitPanelView())
        except discord.HTTPException:
            await interaction.followup.send(
                f"I can't post in {channel.mention}. Check the bot's permissions there.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"Submit panel posted in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SubmissionsCog(bot))
