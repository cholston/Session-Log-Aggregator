"""
Archimedes The Wonder Dragon — standalone Discord bot entry point.

Usage:
    python3 archimedes.py

Requires DISCORD_BOT_TOKEN in .env (or the environment) and
[discord] guild_id + session_channel_id in session_config.toml.
"""

import asyncio
import sys

from archimedes.bot import ArchimedesBot
from modules.config import load_config


async def main():
    config = load_config()

    if not config.discord.token:
        print("ERROR: DISCORD_BOT_TOKEN is not set in .env")
        sys.exit(1)

    bot = ArchimedesBot(config)
    async with bot:
        await bot.start(config.discord.token)


if __name__ == "__main__":
    asyncio.run(main())
