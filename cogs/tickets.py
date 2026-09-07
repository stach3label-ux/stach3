"""Vektra Open - support ticket commands."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import database as store
from core import ui
from core.config import COLOR_BLURPLE, TICKET_STATUSES
from utils.helpers import parse_ticket_code

logger = logging.getLogger("vektra-open.tickets")

_STATUS_CHOICES = [app_commands.Choice(name=status, value=status) for status in TICKET_STATUSES]


class TicketsCog(commands.Cog, name="Tickets"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ticket_panel", description="Admin: post a public 'Open a Ticket' button panel")
    @app_commands.describe(channel="Channel where members open tickets")
    async def ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title=f"{interaction.guild.name} Support",
            description="Need help? Open a ticket and staff will reply by DM.",
            color=COLOR_BLURPLE,
        )
        try:
            await channel.send(embed=embed, view=ui.SupportTicketPanelView())
        except discord.HTTPException:
            await interaction.followup.send(
                f"I can't post in {channel.mention}. Check the bot's permissions there.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"Ticket panel posted in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="tickets", description="Staff: list support tickets")
    @app_commands.describe(status="Optional status filter")
    @app_commands.choices(status=_STATUS_CHOICES)
    async def tickets(self, interaction: discord.Interaction, status: str = ""):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        rows = store.list_tickets(interaction.guild_id, status=status or None, limit=15)
        await interaction.followup.send(embed=ui.tickets_list_embed(rows), ephemeral=True)

    @app_commands.command(name="ticket_set", description="Staff: change a support ticket's status")
    @app_commands.describe(ticket="Support ticket code", new_status="New status")
    @app_commands.choices(new_status=_STATUS_CHOICES)
    async def ticket_set(self, interaction: discord.Interaction, ticket: str, new_status: str):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        code = parse_ticket_code(ticket)
        row = store.fetch_ticket(interaction.guild_id, code)
        if not row:
            await interaction.response.send_message(f"No ticket found for `{code}`.", ephemeral=True)
            return
        store.set_ticket_status(interaction.guild_id, code, new_status)
        await interaction.response.send_message(
            f"`{code}` set to **{new_status}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
