"""Vektra Open - server setup, status and help commands."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import database as store
from core import ui
from core.config import BOT_COMMUNITY_LINK, COLOR_BLURPLE

logger = logging.getLogger("vektra-open.admin")


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup_staff", description="Set the private channel where submission cards appear")
    @app_commands.describe(channel="The private staff review channel")
    async def setup_staff(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You need Administrator or Manage Server permission.", ephemeral=True)
            return
        store.set_staff_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"✅ Submission cards will now be posted in {channel.mention}.",
            ephemeral=True,
        )
        logger.info("guild %s set staff channel to %s", interaction.guild_id, channel.id)

    @app_commands.command(name="setup_ticket_channel", description="Set the private channel where support tickets appear")
    @app_commands.describe(channel="The private staff channel for support tickets")
    async def setup_ticket_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You need Administrator or Manage Server permission.", ephemeral=True)
            return
        store.set_ticket_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"✅ Support ticket cards will now be posted in {channel.mention}.",
            ephemeral=True,
        )
        logger.info("guild %s set ticket channel to %s", interaction.guild_id, channel.id)

    @app_commands.command(name="status", description="Show this server's Vektra setup and current numbers")
    async def status(self, interaction: discord.Interaction):
        if not ui.user_can_manage(interaction):
            await interaction.response.send_message("You need Administrator or Manage Server permission.", ephemeral=True)
            return
        guild = interaction.guild
        config = store.get_guild_config(guild.id)
        staff_id = config.get("staff_channel_id")
        ticket_id = config.get("ticket_channel_id")
        totals = store.guild_totals(guild.id)
        open_tickets = len(store.list_tickets(guild.id, status="Open", limit=100))

        embed = discord.Embed(title=f"{guild.name} — Status", color=COLOR_BLURPLE)
        staff_text = guild.get_channel(staff_id).mention if staff_id and guild.get_channel(staff_id) else "Not set"
        ticket_text = guild.get_channel(ticket_id).mention if ticket_id and guild.get_channel(ticket_id) else "Not set"
        embed.add_field(name="Staff Channel", value=staff_text, inline=True)
        embed.add_field(name="Ticket Channel", value=ticket_text, inline=True)
        embed.add_field(
            name="Submissions",
            value=(
                f"In Queue: **{totals.get('In Queue', 0)}**\n"
                f"Approved: **{totals.get('Approved', 0)}**\n"
                f"Rejected: **{totals.get('Rejected', 0)}**"
            ),
            inline=False,
        )
        embed.add_field(name="Open Tickets", value=str(open_tickets), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="Show what Vektra Open can do")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Vektra Open — Help",
            description=(
                "A self-hosted A&R intake bot for labels. One Postgres database, "
                "one bot token, runs on any small VPS."
            ),
            color=COLOR_BLURPLE,
        )
        embed.add_field(
            name="Artists",
            value="`/submit` send a demo • `/my_submissions` your tickets • `/my_stats` acceptance stats",
            inline=False,
        )
        embed.add_field(
            name="Staff",
            value=(
                "`/queue` newest demos • `/recent` latest activity • `/submission` full detail "
                "• `/tickets` support tickets • `/ticket_set` change a ticket status"
            ),
            inline=False,
        )
        embed.add_field(
            name="Admins",
            value=(
                "`/setup_staff` review channel • `/setup_ticket_channel` ticket channel • "
                "`/post_submit_panel` public submit button • `/ticket_panel` public ticket button "
                "• `/status` overview"
            ),
            inline=False,
        )
        embed.add_field(name="Music (optional)", value="`/play` `/skip` `/stop` `/pause` `/queue` `/volume` `/nowplaying`", inline=False)
        embed.set_footer(text=f"Open source • {BOT_COMMUNITY_LINK}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
