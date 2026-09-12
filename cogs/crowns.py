import discord
from discord import app_commands
from discord.ext import commands

from utils.leaderboard import generate_count_board_embed
from utils.range_filters import (
    MONTH_CHOICES, ERA_CHOICES, QUARTER_CHOICES, SEASON_CHOICES, window_kwargs,
)

class CrownsCog(commands.Cog):
    """Crown leaderboard showing first-place finishes."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    @app_commands.describe(
        year="Specific year to filter by",
        month="Specific month (uses current year if year is omitted)",
        min_games="Only include users with at least this many games in the window",
        era="current (Wordle #1777+, default) or legacy (pre-#1777)",
        season="current season (default) or all for the full era",
        quarter="Specific quarter to show (uses current year if year is omitted; overrides month)",
    )
    @app_commands.choices(
        month=MONTH_CHOICES, era=ERA_CHOICES,
        season=SEASON_CHOICES, quarter=QUARTER_CHOICES,
    )
    async def crowns(
        self,
        interaction: discord.Interaction,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
        quarter: app_commands.Choice[int] = None,
        season: app_commands.Choice[str] = None,
        min_games: app_commands.Range[int, 1, 10000] = None,
        era: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        embed, empty = await generate_count_board_embed(
            self.bot,
            table="crowns",
            title="👑 Crown Leaderboard 👑",
            value_label="Crowns 👑",
            colour=0xf1c40f,
            empty_message="👑 No crown data for this range.",
            window=window_kwargs(season, year, month, quarter),
            era=era.value if era else "current",
            min_games=min_games,
            guild=interaction.guild,
        )
        if empty:
            await interaction.followup.send(empty)
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))
