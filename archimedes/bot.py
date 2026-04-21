"""
Archimedes The Wonder Dragon — Discord bot core.

Loads all cogs from archimedes/cogs/ and syncs slash commands to the
configured guild on startup (instant) and globally (up to 1 hour to propagate).
"""

import discord
from discord.ext import commands

# All cog modules to load at startup
COGS = [
    "archimedes.cogs.session",
    "archimedes.cogs.wonder_dragon",
]


class ArchimedesBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config

    async def setup_hook(self):
        for cog in COGS:
            await self.load_extension(cog)
            print(f"  Loaded cog: {cog}")

        # Sync to guild immediately (instant); global sync can take up to an hour
        if self.config.discord.guild_id:
            guild = discord.Object(id=self.config.discord.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"  Synced {len(synced)} slash command(s) to guild {self.config.discord.guild_id}")

    async def on_ready(self):
        print(f"\nArchimedes The Wonder Dragon awakens as {self.user} (id: {self.user.id})")
        print(f"Watching {len(self.guilds)} guild(s).")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Watching for netsplits.",
            )
        )
