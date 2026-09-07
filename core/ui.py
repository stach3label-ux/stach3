"""Vektra Open - shared Discord embeds, views and modals.

Persistent views (timeout=None) must be re-registered on every bot start via
bot.add_view(...) in bot.py. Buttons read the ticket code back from the embed's
"Ticket" field, so they keep working across restarts.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from core import database as store
from core.config import COLOR_BLURPLE, COLOR_GREEN, COLOR_RED
from utils.helpers import is_valid_url, parse_ticket_code, truncate_text

logger = logging.getLogger("vektra-open.ui")

TICKET_FIELD = "Ticket"


# ── permissions ──────────────────────────────────────────────────────────────

def user_can_manage(interaction: discord.Interaction) -> bool:
    """Staff = server owner, Administrator, or Manage Server permission."""
    user = interaction.user
    if not interaction.guild or not isinstance(user, discord.Member):
        return False
    if user.id == interaction.guild.owner_id:
        return True
    perms = user.guild_permissions
    return bool(perms.administrator or perms.manage_guild)


# ── embed helpers ────────────────────────────────────────────────────────────

def status_color(status: str, default: int = COLOR_BLURPLE) -> int:
    lowered = (status or "").lower()
    if "approv" in lowered:
        return COLOR_GREEN
    if "reject" in lowered:
        return COLOR_RED
    return default


def code_from_embed(embed: discord.Embed) -> str:
    for field in embed.fields:
        if field.name.strip().lower() == TICKET_FIELD.lower():
            return parse_ticket_code(field.value)
    return ""


def set_embed_field(embed: discord.Embed, name: str, value: str, inline: bool = False) -> None:
    """Set (or add) a field on an existing embed by name."""
    for index, field in enumerate(embed.fields):
        if field.name.strip().lower() == name.strip().lower():
            embed.set_field_at(index, name=name, value=value, inline=inline)
            return
    embed.add_field(name=name, value=value, inline=inline)


# ── submission embeds ────────────────────────────────────────────────────────

def submission_card_embed(row: dict, server_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="New Label Submission",
        description=f"**{server_name}** demo intake",
        color=COLOR_BLURPLE,
    )
    embed.add_field(name=TICKET_FIELD, value=f"`{row['ticket_code']}`", inline=False)
    embed.add_field(name="User ID", value=str(row["artist_id"] or "—"), inline=False)
    embed.add_field(name="Name", value=truncate_text(row["artist_name"], 100), inline=True)
    embed.add_field(name="Discord Username", value=truncate_text(row["artist_username"] or "—", 100), inline=True)
    embed.add_field(name="Track Name", value=truncate_text(row["track_name"], 200), inline=False)
    embed.add_field(name="Artist Names", value=truncate_text(row["artists"] or "—", 300), inline=False)
    embed.add_field(name="Demo Link", value=truncate_text(row["demo_link"], 500), inline=False)
    embed.add_field(name="Status", value="In Queue", inline=True)
    embed.add_field(name="Message", value=truncate_text(row["message"] or "—", 700), inline=False)
    if row.get("spam_flagged"):
        embed.add_field(name="Spam Screening", value="⚠️ Flagged by AI moderation - review carefully.", inline=False)
    embed.set_footer(text=f"{server_name} • Pending Action")
    return embed


def submission_list_embed(rows: list[dict], title: str) -> discord.Embed:
    embed = discord.Embed(title=title, color=COLOR_BLURPLE)
    if not rows:
        embed.description = "No submissions found."
        return embed
    for row in rows:
        embed.add_field(
            name=f"`{row['ticket_code']}` • {truncate_text(row['track_name'], 90)}",
            value=(
                f"Artists: {truncate_text(row['artists'] or row['artist_name'], 150)}\n"
                f"Status: **{row['status']}**\n"
                f"Submitter: {truncate_text(row['artist_name'], 100)}"
            ),
            inline=False,
        )
    return embed


def submission_detail_embed(row: dict, server_name: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Submission {row['ticket_code']}",
        description=f"**{truncate_text(row['track_name'], 200)}**",
        color=status_color(row["status"]),
    )
    embed.add_field(name=TICKET_FIELD, value=f"`{row['ticket_code']}`", inline=False)
    embed.add_field(name="Status", value=row["status"], inline=True)
    embed.add_field(name="Submitter", value=truncate_text(row["artist_name"], 120), inline=True)
    embed.add_field(name="Discord", value=truncate_text(row["artist_username"] or "—", 120), inline=True)
    embed.add_field(name="Artists", value=truncate_text(row["artists"] or "—", 400), inline=False)
    embed.add_field(name="Demo Link", value=truncate_text(row["demo_link"], 600), inline=False)
    embed.add_field(name="Message", value=truncate_text(row["message"] or "—", 700), inline=False)
    if row.get("reason"):
        embed.add_field(name="Decision Note", value=truncate_text(row["reason"], 700), inline=False)
    embed.set_footer(text=f"{server_name} • {row['created_at']:%Y-%m-%d %H:%M}")
    return embed


def my_submissions_embed(rows: list[dict], server_name: str) -> discord.Embed:
    embed = discord.Embed(title=f"My Submissions — {server_name}", color=COLOR_BLURPLE)
    if not rows:
        embed.description = "You have not submitted any demos in this server yet."
        return embed
    for row in rows:
        embed.add_field(
            name=f"`{row['ticket_code']}` • {truncate_text(row['track_name'], 90)}",
            value=f"Status: **{row['status']}**\nTicket: `{row['ticket_code']}`",
            inline=False,
        )
    return embed


# ── ticket embeds ────────────────────────────────────────────────────────────

def ticket_card_embed(row: dict, server_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="New Support Ticket",
        description=f"**{server_name}** support",
        color=COLOR_BLURPLE,
    )
    embed.add_field(name=TICKET_FIELD, value=f"`{row['ticket_code']}`", inline=False)
    embed.add_field(name="Status", value=row["status"], inline=True)
    embed.add_field(name="User", value=truncate_text(row["username"] or "—", 120), inline=True)
    embed.add_field(name="Subject", value=truncate_text(row["subject"], 200), inline=False)
    embed.add_field(name="Message", value=truncate_text(row["body"] or "—", 700), inline=False)
    embed.set_footer(text=f"{server_name} • Ticket {row['ticket_code']}")
    return embed


def tickets_list_embed(rows: list[dict]) -> discord.Embed:
    embed = discord.Embed(title="Support Tickets", color=COLOR_BLURPLE)
    if not rows:
        embed.description = "No tickets found."
        return embed
    for row in rows:
        embed.add_field(
            name=f"`{row['ticket_code']}` • {row['status']}",
            value=(
                f"{truncate_text(row['subject'], 120)}\n"
                f"Opened by {truncate_text(row['username'] or '—', 100)}\n"
                f"Updated: {row['updated_at']:%Y-%m-%d %H:%M}"
            ),
            inline=False,
        )
    return embed


# ── DM content helpers ───────────────────────────────────────────────────────

async def dm_user(client: discord.Client, user_id: int | None, embed: discord.Embed) -> bool:
    if not user_id:
        return False
    user = client.get_user(user_id)
    if user is None:
        try:
            user = await client.fetch_user(user_id)
        except discord.HTTPException:
            return False
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def post_to_thread(client: discord.Client, thread_id: int | None, text: str) -> bool:
    """Best-effort post into a staff thread (unarchives if needed)."""
    if not thread_id:
        return False
    thread = client.get_channel(thread_id)
    if thread is None:
        try:
            thread = await client.fetch_channel(thread_id)
        except discord.HTTPException:
            return False
    try:
        if getattr(thread, "archived", False):
            await thread.edit(archived=False)
        await thread.send(text)
        return True
    except discord.HTTPException:
        logger.warning("Could not post to thread %s.", thread_id, exc_info=True)
        return False


async def make_thread(message: discord.Message, name: str) -> discord.Thread | None:
    try:
        return await message.create_thread(name=truncate_text(name, 90), auto_archive_duration=1440)
    except discord.HTTPException:
        logger.warning("Could not create thread under message %s.", message.id)
        return None


# ── modals ───────────────────────────────────────────────────────────────────

class SubmissionModal(discord.ui.Modal, title="New Label Submission"):
    real_name = discord.ui.TextInput(
        label="Your Real Name",
        placeholder="e.g. Marcus Soune",
        max_length=100,
    )
    track_name = discord.ui.TextInput(
        label="Track Name",
        placeholder="e.g. FOURTEY FUNK",
        max_length=100,
    )
    demo_link = discord.ui.TextInput(
        label="Demo Link",
        placeholder="https://soundcloud.com/... or https://drive.google.com/...",
        max_length=500,
    )
    artist_names = discord.ui.TextInput(
        label="Artist Names",
        placeholder="e.g. main artist, featured artist",
        max_length=300,
        required=False,
    )
    message = discord.ui.TextInput(
        label="Message to Label",
        placeholder="Extra notes about your track (optional)...",
        style=discord.TextStyle.paragraph,
        max_length=700,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Run this inside a server.", ephemeral=True)
            return

        staff_channel_id = store.get_staff_channel_id(guild.id)
        if not staff_channel_id:
            await interaction.followup.send(
                "This server hasn't set a staff channel yet. Ask an admin to run `/setup_staff`.",
                ephemeral=True,
            )
            return
        channel = interaction.client.get_channel(staff_channel_id) or guild.get_channel(staff_channel_id)
        if channel is None:
            await interaction.followup.send(
                "Error: I can't see the configured staff channel. Check the bot's permissions there.",
                ephemeral=True,
            )
            return

        demo_link = self.demo_link.value.strip()
        if not is_valid_url(demo_link):
            await interaction.followup.send(
                "Please enter a valid demo link starting with http:// or https://.",
                ephemeral=True,
            )
            return

        duplicate = store.duplicate_demo(guild.id, demo_link)
        if duplicate:
            await interaction.followup.send(
                "That demo link was already submitted in this server. "
                f"Existing ticket: `{duplicate['ticket_code']}` (status: **{duplicate['status']}**).",
                ephemeral=True,
            )
            return

        flagged = False
        try:
            from core.moderation import screen_submission
            if screen_submission is not None:
                result = await asyncio.to_thread(
                    screen_submission,
                    real_name=self.real_name.value,
                    track_name=self.track_name.value,
                    artist_names=self.artist_names.value,
                    demo_link=demo_link,
                    message=self.message.value,
                )
                flagged = bool(result.get("flagged"))
        except Exception:
            logger.exception("AI spam screening failed - submitting anyway.")

        row = store.create_submission(
            guild.id,
            artist_id=interaction.user.id,
            artist_name=self.real_name.value.strip(),
            artist_username=str(interaction.user),
            track_name=self.track_name.value.strip(),
            artists=self.artist_names.value.strip(),
            demo_link=demo_link,
            message=self.message.value.strip() or "No extra notes.",
            spam_flagged=flagged,
        )
        if not row:
            await interaction.followup.send("I could not save your submission. Try again later.", ephemeral=True)
            return

        embed = submission_card_embed(row, guild.name)
        try:
            card = await channel.send(embed=embed, view=SubmissionDecisionView())
        except discord.HTTPException:
            logger.exception("Could not post submission card for %s.", row["ticket_code"])
            await interaction.followup.send(
                "I saved your submission, but I couldn't post the staff card. "
                "Ask an admin to give the bot Send Messages + Embed Links in the staff channel.",
                ephemeral=True,
            )
            return

        thread = await make_thread(card, f"{row['ticket_code']} • {row['track_name']}")
        if thread:
            store.set_submission_thread(guild.id, row["ticket_code"], thread.id)
            await thread.send("Staff discussion thread for this submission. Decisions and replies are logged here.")

        await interaction.followup.send(
            f"✅ Your demo **{truncate_text(self.track_name.value, 100)}** was submitted to **{guild.name}**.\n"
            f"Ticket: `{row['ticket_code']}` — you'll be updated here when staff decide.",
            ephemeral=True,
        )
        await dm_user(
            interaction.client,
            interaction.user.id,
            discord.Embed(
                title="Submission Received",
                description=(
                    f"Your demo **{truncate_text(self.track_name.value, 100)}** was received by **{guild.name}**.\n"
                    f"Ticket: `{row['ticket_code']}`\nStatus: **In Queue**"
                ),
                color=COLOR_BLURPLE,
            ),
        )


class RejectReasonModal(discord.ui.Modal, title="Reject Submission"):
    reason = discord.ui.TextInput(
        label="Reason for the artist",
        placeholder="Short reason - this is sent to the artist.",
        style=discord.TextStyle.paragraph,
        max_length=600,
        required=True,
    )

    def __init__(self, guild_id: int, code: str, card: discord.Message | None = None):
        super().__init__()
        self.guild_id = guild_id
        self.code = code
        self.card = card

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        code = self.code
        row = store.fetch_submission(self.guild_id, code)
        if not row:
            await interaction.followup.send("That submission no longer exists.", ephemeral=True)
            return
        if row["status"] != "In Queue":
            await interaction.followup.send(
                f"This submission was already {row['status'].lower()}.", ephemeral=True
            )
            return
        reason = self.reason.value.strip() or "No specific reason was given."
        store.decide_submission(self.guild_id, code, "Rejected", reason=reason)

        embed = discord.Embed(
            title="Submission Update",
            description=(
                f"Hi **{row['artist_name']}**, thanks for sending **{truncate_text(row['track_name'], 150)}** "
                f"to **{interaction.guild.name if interaction.guild else 'the label'}**.\n\n"
                f"Unfortunately this one isn't the right fit right now.\n\n**Reason:** {truncate_text(reason, 600)}"
            ),
            color=COLOR_RED,
        )
        embed.set_footer(text=f"Ticket {code}")
        await dm_user(interaction.client, row["artist_id"], embed)
        await post_to_thread(
            interaction.client,
            row["staff_thread_id"],
            f"❌ Rejected by {interaction.user.mention}. Reason: {truncate_text(reason, 600)}",
        )
        await self._update_card(interaction, row, "Rejected", reason)
        await interaction.followup.send("Submission rejected and the artist was notified.", ephemeral=True)

    async def _update_card(self, interaction, row, status, reason):
        message = self.card
        if not message or not message.embeds:
            return
        embed = message.embeds[0]
        embed.color = status_color(status)
        set_embed_field(embed, "Status", status, inline=True)
        set_embed_field(embed, "Decision Note", truncate_text(reason, 600), inline=False)
        embed.set_footer(text=f"Rejected by @{interaction.user.name}")
        try:
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            logger.warning("Could not edit card for %s after reject.", row["ticket_code"])
        except discord.NotFound:
            logger.warning("Card message for %s is gone.", row["ticket_code"])


class StaffMessageModal(discord.ui.Modal, title="Send a Message"):
    body = discord.ui.TextInput(
        label="Message",
        placeholder="What would you like to tell them?",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=True,
    )

    def __init__(self, kind: str, guild_id: int, code: str):
        super().__init__()
        self.kind = kind  # "submission" | "ticket"
        self.guild_id = guild_id
        self.code = code

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.kind == "submission":
            row = store.fetch_submission(self.guild_id, self.code)
            if not row:
                await interaction.followup.send("That submission no longer exists.", ephemeral=True)
                return
            prefix = f"Message from **{interaction.guild.name if interaction.guild else 'the label'}** about your submission **{truncate_text(row['track_name'], 150)}** (`{self.code}`)"
            await post_to_thread(
                interaction.client,
                row["staff_thread_id"],
                f"💬 DM sent by {interaction.user.mention}: {truncate_text(self.body.value, 1400)}",
            )
        elif self.kind == "ticket":
            row = store.fetch_ticket(self.guild_id, self.code)
            if not row:
                await interaction.followup.send("That ticket no longer exists.", ephemeral=True)
                return
            prefix = f"Message from **{interaction.guild.name if interaction.guild else 'staff'}** about your support ticket (`{self.code}`)"
            await post_to_thread(
                interaction.client,
                row["thread_id"],
                f"💬 DM sent by {interaction.user.mention}: {truncate_text(self.body.value, 1400)}",
            )
        else:
            await interaction.followup.send("Unknown action.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Message from Staff",
            description=f"{prefix}\n\n{self.body.value}",
            color=COLOR_BLURPLE,
        )
        embed.set_footer(text=f"Ticket {self.code}")
        if self.kind == "ticket":
            embed.description += "\n\n💬 Tip: you can reply directly by DMing this bot - staff will see it in the thread."
        sent = await dm_user(interaction.client, row.get("artist_id") or row.get("user_id"), embed)
        await interaction.followup.send(
            "Message delivered to them." if sent else "I couldn't DM them - they may have DMs closed.",
            ephemeral=True,
        )


class TicketModal(discord.ui.Modal, title="Open a Support Ticket"):
    subject = discord.ui.TextInput(
        label="Subject",
        placeholder="What do you need help with?",
        max_length=120,
    )
    body = discord.ui.TextInput(
        label="Details",
        placeholder="Describe the issue or question...",
        style=discord.TextStyle.paragraph,
        max_length=700,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Run this inside a server.", ephemeral=True)
            return
        ticket_channel_id = store.get_ticket_channel_id(guild.id)
        if not ticket_channel_id:
            await interaction.followup.send(
                "This server hasn't set up support tickets. Ask an admin to run `/setup_ticket_channel`.",
                ephemeral=True,
            )
            return
        channel = interaction.client.get_channel(ticket_channel_id) or guild.get_channel(ticket_channel_id)
        if channel is None:
            await interaction.followup.send(
                "I can't see the configured ticket channel. Check permissions and run `/setup_ticket_channel` again.",
                ephemeral=True,
            )
            return

        row = store.create_ticket(
            guild.id,
            user_id=interaction.user.id,
            username=str(interaction.user),
            subject=self.subject.value.strip(),
            body=self.body.value.strip() or "No additional details.",
        )
        if not row:
            await interaction.followup.send("I could not open the ticket. Try again later.", ephemeral=True)
            return

        embed = ticket_card_embed(row, guild.name)
        try:
            card = await channel.send(embed=embed, view=TicketStaffView())
        except discord.HTTPException:
            logger.exception("Could not post ticket card for %s.", row["ticket_code"])
            await interaction.followup.send(
                "I created your ticket but couldn't post it for staff. Ask an admin to check bot permissions.",
                ephemeral=True,
            )
            return
        thread = await make_thread(card, f"{row['ticket_code']} • {row['subject']}")
        if thread:
            store.set_ticket_thread(guild.id, row["ticket_code"], thread.id)
            await thread.send("Staff discussion thread for this ticket.")

        await dm_user(
            interaction.client,
            interaction.user.id,
            discord.Embed(
                title="Support Ticket Opened",
                description=(
                    f"Your ticket with **{guild.name}** is open.\nTicket: `{row['ticket_code']}`\n\n"
                    "Staff will reply by DM. You can reply by DMing this bot directly - "
                    "your messages are forwarded to the staff thread."
                ),
                color=COLOR_BLURPLE,
            ),
        )
        await interaction.followup.send(
            f"✅ Ticket `{row['ticket_code']}` opened with **{guild.name}**. Staff will get back to you shortly.",
            ephemeral=True,
        )


# ── persistent views ─────────────────────────────────────────────────────────

class SubmissionDecisionView(discord.ui.View):
    """Approve / Reject / DM buttons on a submission staff card."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="submission:approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not user_can_manage(interaction) or not interaction.guild:
            await interaction.followup.send("You don't have permission to do that.", ephemeral=True)
            return
        code = code_from_embed(interaction.message.embeds[0]) if interaction.message and interaction.message.embeds else ""
        if not code:
            await interaction.followup.send("Could not read this card.", ephemeral=True)
            return
        row = store.fetch_submission(interaction.guild_id, code)
        if not row or row["status"] != "In Queue":
            await interaction.followup.send("This submission was already decided.", ephemeral=True)
            return

        store.decide_submission(interaction.guild_id, code, "Approved")
        guild_name = interaction.guild.name
        embed = discord.Embed(
            title="Submission Approved 🎉",
            description=(
                f"Congratulations **{row['artist_name']}** — **{truncate_text(row['track_name'], 150)}** "
                f"was approved by **{guild_name}**!\n\n"
                "The team will reach out with next steps."
            ),
            color=COLOR_GREEN,
        )
        embed.set_footer(text=f"Ticket {code}")
        sent = await dm_user(interaction.client, row["artist_id"], embed)
        await post_to_thread(
            interaction.client,
            row["staff_thread_id"],
            f"✅ Approved by {interaction.user.mention}. Artist notified: {'yes' if sent else 'no'}.",
        )
        card = interaction.message
        old = card.embeds[0]
        old.color = COLOR_GREEN
        set_embed_field(old, "Status", "Approved", inline=True)
        old.set_footer(text=f"Approved by @{interaction.user.name} • Artist notified: {'yes' if sent else 'no'}")
        await card.edit(embed=old, view=None)
        await interaction.followup.send("Approved and processed.", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="submission:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not user_can_manage(interaction) or not interaction.guild:
            await interaction.response.send_message("You don't have permission to do that.", ephemeral=True)
            return
        code = code_from_embed(interaction.message.embeds[0]) if interaction.message and interaction.message.embeds else ""
        if not code:
            await interaction.response.send_message("Could not read this card.", ephemeral=True)
            return
        row = store.fetch_submission(interaction.guild_id, code)
        if not row or row["status"] != "In Queue":
            await interaction.response.send_message("This submission was already decided.", ephemeral=True)
            return
        await interaction.response.send_modal(
            RejectReasonModal(interaction.guild_id, code, card=interaction.message)
        )

    @discord.ui.button(label="DM", style=discord.ButtonStyle.blurple, custom_id="submission:dm")
    async def dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not user_can_manage(interaction) or not interaction.guild:
            await interaction.response.send_message("You don't have permission to do that.", ephemeral=True)
            return
        code = code_from_embed(interaction.message.embeds[0]) if interaction.message and interaction.message.embeds else ""
        if not code:
            await interaction.response.send_message("Could not read this card.", ephemeral=True)
            return
        await interaction.response.send_modal(StaffMessageModal("submission", interaction.guild_id, code))


class TicketStaffView(discord.ui.View):
    """Resolve / DM buttons on a support ticket card."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Resolve", style=discord.ButtonStyle.green, custom_id="ticket:resolve")
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not user_can_manage(interaction) or not interaction.guild:
            await interaction.followup.send("You don't have permission to do that.", ephemeral=True)
            return
        code = code_from_embed(interaction.message.embeds[0]) if interaction.message and interaction.message.embeds else ""
        if not code:
            await interaction.followup.send("Could not read this card.", ephemeral=True)
            return
        row = store.fetch_ticket(interaction.guild_id, code)
        if not row or row["status"] == "Resolved":
            await interaction.followup.send("This ticket was already resolved.", ephemeral=True)
            return
        store.set_ticket_status(interaction.guild_id, code, "Resolved")
        sent = await dm_user(
            interaction.client,
            row["user_id"],
            discord.Embed(
                title="Ticket Resolved",
                description=f"Your ticket `{code}` with **{interaction.guild.name}** was marked as resolved.",
                color=COLOR_GREEN,
            ),
        )
        await post_to_thread(
            interaction.client,
            row["thread_id"],
            f"✅ Resolved by {interaction.user.mention}. User notified: {'yes' if sent else 'no'}.",
        )
        card = interaction.message
        old = card.embeds[0]
        old.color = COLOR_GREEN
        set_embed_field(old, "Status", "Resolved", inline=True)
        old.set_footer(text=f"Resolved by @{interaction.user.name}")
        await card.edit(embed=old, view=None)
        await interaction.followup.send("Ticket resolved.", ephemeral=True)

    @discord.ui.button(label="DM User", style=discord.ButtonStyle.blurple, custom_id="ticket:dm")
    async def dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not user_can_manage(interaction) or not interaction.guild:
            await interaction.response.send_message("You don't have permission to do that.", ephemeral=True)
            return
        code = code_from_embed(interaction.message.embeds[0]) if interaction.message and interaction.message.embeds else ""
        if not code:
            await interaction.response.send_message("Could not read this card.", ephemeral=True)
            return
        await interaction.response.send_modal(StaffMessageModal("ticket", interaction.guild_id, code))


class SubmitPanelView(discord.ui.View):
    """One-button 'Submit a Demo' panel - posts wherever an admin wants."""

    def __init__(self, label: str = "Submit a Demo"):
        super().__init__(timeout=None)
        self._label = label

    @discord.ui.button(label="Submit a Demo", style=discord.ButtonStyle.blurple, custom_id="submit:open")
    async def open_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("This panel only works inside a server.", ephemeral=True)
            return
        await interaction.response.send_modal(SubmissionModal())


class SupportTicketPanelView(discord.ui.View):
    """One-button 'Open a Ticket' panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.gray, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("This panel only works inside a server.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketModal())
