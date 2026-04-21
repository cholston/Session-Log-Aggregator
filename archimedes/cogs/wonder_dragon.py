"""
WonderDragon cog — posts ASCII art of Archimedes to the channel.

/WonderDragon  — emit the configured ASCII art file into the current channel.
"""

import os

import discord
from discord import app_commands
from discord.ext import commands

_CHUNK_SIZE = 1900  # stay safely under Discord's 2000-char message limit


def _chunks(text: str, size: int) -> list[str]:
    """Split text into chunks that each fit inside a Discord code block."""
    lines, current, result = text.splitlines(keepends=True), [], []
    for line in lines:
        if sum(len(l) for l in current) + len(line) > size:
            result.append("".join(current))
            current = []
        current.append(line)
    if current:
        result.append("".join(current))
    return result


class WonderDragonCog(commands.Cog, name="WonderDragon"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="wonderdragon",
        description="Summon Archimedes The Wonder Dragon",
    )
    async def wonder_dragon(self, interaction: discord.Interaction):
        art_path = self.bot.config.discord.wonder_dragon_art_path

        if not art_path:
            await interaction.response.send_message(
                "No ASCII art configured (`discord.wonder_dragon_art_path` in session_config.toml).",
                ephemeral=True,
            )
            return

        if not os.path.exists(art_path):
            await interaction.response.send_message(
                f"Art file not found: `{art_path}`",
                ephemeral=True,
            )
            return

        with open(art_path, "r", encoding="utf-8") as f:
            art = f.read()

        parts = _chunks(art, _CHUNK_SIZE)

        await interaction.response.defer()
        await interaction.followup.send(f"```\n{parts[0]}\n```")
        for part in parts[1:]:
            await interaction.channel.send(f"```\n{part}\n```")


async def setup(bot):
    await bot.add_cog(WonderDragonCog(bot))
