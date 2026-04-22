import discord
from discord import app_commands
from discord.ext import commands
from utils.parsing import calculate_streak, longest_streak
from utils.admin_helpers import NOT_VOIDED_SQL, load_voided_set
from utils.range_filters import MONTH_CHOICES, RANGE_CHOICES, build_date_filter

class StreaksCog(commands.Cog):
    """Commands for viewing individual and top streaks."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="streak", description="Show your current Wordle streak")
    @app_commands.describe(
        range="Relative window: week, month, year — reports longest run inside it",
        year="Specific year (reports longest run inside it)",
        month="Specific month (uses current year if year is omitted)",
    )
    @app_commands.choices(range=RANGE_CHOICES, month=MONTH_CHOICES)
    async def streak(
        self,
        interaction: discord.Interaction,
        range: app_commands.Choice[str] = None,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
    ):
        await interaction.response.defer(thinking=True)
        date_filter, title_suffix = build_date_filter(
            range=range.value if range else None,
            year=year,
            month=month.value if month else None,
        )
        windowed = bool(title_suffix)

        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT wordle_number
                FROM scores s
                WHERE s.user_id = $1 AND s.attempts IS NOT NULL
                  AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter}
                ORDER BY wordle_number
            """, interaction.user.id)
            voided = await load_voided_set(conn, interaction.user.id)
        wordles = [r["wordle_number"] for r in rows]

        if windowed:
            n = longest_streak(wordles, voided=voided)
            await interaction.followup.send(
                f"🔥 Longest streak in {title_suffix}: **{n}** Wordles in a row."
            )
        else:
            n = calculate_streak(wordles, voided=voided)
            await interaction.followup.send(
                f"🔥 Your current streak is **{n}** Wordles in a row."
            )

    @app_commands.command(name="streaks", description="Top 15 Wordle streaks")
    @app_commands.describe(
        range="Relative window: week, month, year — ranks by longest run inside it",
        year="Specific year (ranks by longest run inside it)",
        month="Specific month (uses current year if year is omitted)",
    )
    @app_commands.choices(range=RANGE_CHOICES, month=MONTH_CHOICES)
    async def streaks(
        self,
        interaction: discord.Interaction,
        range: app_commands.Choice[str] = None,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
    ):
        await interaction.response.defer(thinking=True)
        date_filter, title_suffix = build_date_filter(
            range=range.value if range else None,
            year=year,
            month=month.value if month else None,
        )
        windowed = bool(title_suffix)

        async with self.bot.pg_pool.acquire() as conn:
            users = await conn.fetch(f"""
                SELECT DISTINCT user_id, username
                FROM scores s
                WHERE s.attempts IS NOT NULL
                  AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter}
            """)
            global_voided_rows = await conn.fetch("SELECT wordle_number FROM voided_wordles")
            global_voided = {r["wordle_number"] for r in global_voided_rows}
            results = []
            for user in users:
                wordles = await conn.fetch(f"""
                    SELECT wordle_number
                    FROM scores s
                    WHERE s.user_id = $1 AND s.attempts IS NOT NULL
                      AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                      AND {NOT_VOIDED_SQL.format(alias='s')}
                      {date_filter}
                    ORDER BY wordle_number
                """, user["user_id"])
                user_voided_rows = await conn.fetch(
                    "SELECT wordle_number FROM voided_user_wordles WHERE user_id = $1",
                    user["user_id"],
                )
                voided = global_voided | {r["wordle_number"] for r in user_voided_rows}
                wordle_nums = [r["wordle_number"] for r in wordles]
                streak_count = (
                    longest_streak(wordle_nums, voided=voided)
                    if windowed
                    else calculate_streak(wordle_nums, voided=voided)
                )
                if streak_count > 0:
                    results.append((user["username"], streak_count))
        results.sort(key=lambda x: x[1], reverse=True)

        if windowed:
            title = f"🔥 Longest Streaks ({title_suffix}) 🔥"
        else:
            title = "🔥 Top Streaks 🔥"
        embed = discord.Embed(title=title, color=0xff9900)
        for idx, (user, streak_count) in enumerate(results[:15], start=1):
            embed.add_field(name=f"#{idx} {user}", value=f"{streak_count} in a row", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(StreaksCog(bot))
