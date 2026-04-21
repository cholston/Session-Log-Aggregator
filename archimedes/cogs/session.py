"""
Session cog — slash commands for scheduling and announcing TTRPG sessions.

Commands:
  /schedule-session  — create a Discord guild scheduled event
  /session-recap     — post a session notes URL to the session channel
"""

from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands


class SessionCog(commands.Cog, name="Session"):
    def __init__(self, bot):
        self.bot = bot

    # ----------------------------------------------------------------------- #
    # /schedule-session
    # ----------------------------------------------------------------------- #

    @app_commands.command(
        name="schedule-session",
        description="Create a Discord event for the next TTRPG session",
    )
    @app_commands.describe(
        date='Session date and time, e.g. "2026-04-26 19:00" (local server time)',
        name="Event title (overrides config default)",
        description="Optional event description",
        duration_hours="Session length in hours (default: 2.5)",
    )
    async def schedule_session(
        self,
        interaction: discord.Interaction,
        date: str,
        name: str = "",
        description: str = "",
        duration_hours: float = 2.5,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            start_naive = datetime.strptime(date, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.followup.send(
                'Invalid date format. Use: `YYYY-MM-DD HH:MM` (e.g. `2026-04-26 19:00`)',
                ephemeral=True,
            )
            return

        # Stamp local timezone without converting — the input is local time.
        local_tz = datetime.now().astimezone().tzinfo
        start_time = start_naive.replace(tzinfo=local_tz)
        end_time = start_time + timedelta(hours=duration_hours)

        cfg = self.bot.config.discord
        event_name = name or cfg.event_name
        voice_channel_id = cfg.voice_channel_id
        location = getattr(cfg, "event_location", "FoundryVTT")

        image_bytes: bytes | None = None
        if cfg.event_image_path:
            import os
            if os.path.exists(cfg.event_image_path):
                with open(cfg.event_image_path, "rb") as f:
                    image_bytes = f.read()

        kwargs: dict = dict(
            name=event_name,
            start_time=start_time,
            end_time=end_time,
            privacy_level=discord.PrivacyLevel.guild_only,
            description=description,
        )
        if image_bytes:
            kwargs["image"] = image_bytes

        if voice_channel_id:
            channel = interaction.guild.get_channel(voice_channel_id) or await interaction.guild.fetch_channel(voice_channel_id)
            kwargs["entity_type"] = discord.EntityType.voice
            kwargs["channel"] = channel
        else:
            kwargs["entity_type"] = discord.EntityType.external
            kwargs["location"] = location

        try:
            event = await interaction.guild.create_scheduled_event(**kwargs)
            print(f"  [schedule-session] Event created: id={event.id} name={event.name!r} "
                  f"start={event.start_time} entity_type={event.entity_type} "
                  f"status={event.status} url={event.url}")
        except discord.HTTPException as exc:
            print(f"  [schedule-session] HTTPException {exc.status} {exc.code}: {exc.text}")
            await interaction.followup.send(
                f"Failed to create event: {exc}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Scheduled: **{event.name}** — <t:{int(start_time.timestamp())}:F>",
            ephemeral=True,
        )

    # ----------------------------------------------------------------------- #
    # /session-recap
    # ----------------------------------------------------------------------- #

    @app_commands.command(
        name="session-recap",
        description="Post a session notes link to the session channel",
    )
    @app_commands.describe(
        url="Published session notes URL",
        message="Optional message to accompany the link",
    )
    async def session_recap(
        self,
        interaction: discord.Interaction,
        url: str,
        message: str = "Session notes are up!",
    ):
        channel_id = self.bot.config.discord.session_channel_id
        if not channel_id:
            await interaction.response.send_message(
                "No session channel configured (`discord.session_channel_id` in session_config.toml).",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                await interaction.response.send_message(
                    f"Session channel {channel_id} not found.",
                    ephemeral=True,
                )
                return

        await channel.send(f"{message}\n{url}")
        await interaction.response.send_message("Posted!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SessionCog(bot))
