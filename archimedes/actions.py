"""
One-shot Discord API actions for use by session_wrap.py (and any other caller
that doesn't need a persistent bot process).

Each public function is synchronous — it spins up a temporary Discord client,
performs the action on_ready, then closes.  Safe to call from non-async code.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import discord


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

async def _run_with_client(token: str, coro_factory):
    """
    Start a minimal Discord client, await coro_factory(client) on_ready,
    then close.  Returns whatever coro_factory returns.
    """
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    result_holder: list = []
    error_holder: list = []

    @client.event
    async def on_ready():
        try:
            result_holder.append(await coro_factory(client))
        except Exception as exc:
            error_holder.append(exc)
        finally:
            await client.close()

    await client.start(token)

    if error_holder:
        raise error_holder[0]
    return result_holder[0] if result_holder else None


# --------------------------------------------------------------------------- #
# Public actions
# --------------------------------------------------------------------------- #

def create_session_event(
    token: str,
    guild_id: int,
    name: str,
    start_time: datetime,
    description: str = "",
    duration_hours: float = 2.5,
    voice_channel_id: int = 0,
    image_path: str = "",
    location: str = "FoundryVTT",
) -> int:
    """
    Create a Discord guild scheduled event.

    start_time must be timezone-aware. If it's naive (no tzinfo), it is
    assumed to be local time.

    If voice_channel_id is provided, the event is a voice channel event;
    otherwise it is an external event using `location`.

    Returns the created event's ID.
    """
    import os

    if start_time.tzinfo is None:
        # Stamp local timezone without conversion — the caller passed local time
        local_tz = datetime.now().astimezone().tzinfo
        start_time = start_time.replace(tzinfo=local_tz)

    end_time = start_time + timedelta(hours=duration_hours)

    image_bytes: bytes | None = None
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_bytes = f.read()

    async def _action(client: discord.Client):
        guild = client.get_guild(guild_id) or await client.fetch_guild(guild_id)

        kwargs: dict = dict(
            name=name,
            start_time=start_time,
            end_time=end_time,
            privacy_level=discord.PrivacyLevel.guild_only,
            description=description,
        )
        if image_bytes:
            kwargs["image"] = image_bytes

        if voice_channel_id:
            channel = client.get_channel(voice_channel_id) or await client.fetch_channel(voice_channel_id)
            kwargs["entity_type"] = discord.EntityType.voice
            kwargs["channel"] = channel
        else:
            kwargs["entity_type"] = discord.EntityType.external
            kwargs["location"] = location

        event = await guild.create_scheduled_event(**kwargs)
        print(f"  Discord event created: '{event.name}' (id: {event.id})")
        return event.id

    return asyncio.run(_run_with_client(token, _action))


def post_message(
    token: str,
    channel_id: int,
    message: str,
) -> int:
    """
    Post a message to a Discord channel.  Returns the message ID.
    """
    async def _action(client: discord.Client):
        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        msg = await channel.send(message)
        print(f"  Discord message posted to channel {channel_id} (id: {msg.id})")
        return msg.id

    return asyncio.run(_run_with_client(token, _action))
