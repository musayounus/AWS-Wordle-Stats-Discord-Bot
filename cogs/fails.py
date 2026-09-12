import discord
from discord import app_commands
from discord.ext import commands

from utils.admin_helpers import reject_bad_wordle, wordle_date_for_number
from utils.leaderboard import generate_count_board_embed
from utils.range_filters import (
    MONTH_CHOICES, ERA_CHOICES, QUARTER_CHOICES, SEASON_CHOICES, window_kwargs,
)


class FailsCog(commands.Cog):
    """Track and show Wordle fails (X/6)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="fails_leaderboard",
        description="Show the Wordle fails leaderboard (who's missed Wordle most)"
    )
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
    async def fails_leaderboard(
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
            table="fails",
            title="💀 Wordle Fails Leaderboard",
            value_label="Fails 💀",
            colour=0xff0000,
            empty_message="💀 No fails for this range.",
            window=window_kwargs(season=season, year=year, month=month, quarter=quarter),
            era=era.value if era else "current",
            min_games=min_games,
            guild=interaction.guild,
        )
        if empty:
            await interaction.followup.send(empty)
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="add_fails", description="(Admin-Only) Add a fail (X/6) for a user on a specific Wordle")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_fails(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        if await reject_bad_wordle(interaction, wordle_number):
            return

        date = wordle_date_for_number(wordle_number)

        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
                """,
                user.id, user.display_name, wordle_number, date,
            )
            await conn.execute(
                """
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES ($1, $2, $3, $4, NULL)
                ON CONFLICT (username, wordle_number) DO UPDATE
                SET attempts = NULL
                """,
                user.id, user.display_name, wordle_number, date,
            )

        await interaction.response.send_message(
            f"💀 Added fail for {user.mention} on Wordle #{wordle_number}.",
            ephemeral=True,
        )

    @app_commands.command(name="remove_fails", description="(Admin-Only) Remove a fail (X/6) for a user on a specific Wordle")
    @app_commands.describe(user="User to adjust", wordle_number="Wordle number")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_fails(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        wordle_number: int,
    ):
        if await reject_bad_wordle(interaction, wordle_number):
            return

        async with self.bot.pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
                user.id, wordle_number,
            )
            await conn.execute(
                """
                DELETE FROM scores
                WHERE user_id = $1 AND wordle_number = $2 AND attempts IS NULL
                """,
                user.id, wordle_number,
            )

        await interaction.response.send_message(
            f"💀 Removed fail for {user.mention} on Wordle #{wordle_number}.",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(FailsCog(bot))