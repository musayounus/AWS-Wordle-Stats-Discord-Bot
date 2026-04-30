import discord
from discord import app_commands
from discord.ext import commands
from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import MONTH_CHOICES, ERA_CHOICES, build_date_filter, build_era_filter

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
    )
    @app_commands.choices(month=MONTH_CHOICES, era=ERA_CHOICES)
    async def crowns(
        self,
        interaction: discord.Interaction,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
        min_games: app_commands.Range[int, 1, 10000] = None,
        era: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        era_value = era.value if era else "current"
        date_filter, title_suffix = build_date_filter(
            year=year,
            month=month.value if month else None,
        )
        scores_date_filter, _ = build_date_filter(
            year=year,
            month=month.value if month else None,
            column="sc.date",
        )
        era_filter, era_suffix = build_era_filter(era_value, column="s.wordle_number")
        scores_era_filter, _ = build_era_filter(era_value, column="sc.wordle_number")
        min_games_clause = ""
        if min_games:
            min_games_clause = f"""
                HAVING (
                    SELECT COUNT(*) FROM scores sc
                    WHERE sc.user_id = s.user_id
                      AND sc.user_id NOT IN (SELECT user_id FROM banned_users)
                      AND {NOT_VOIDED_SQL.format(alias='sc')}
                      {scores_date_filter} {scores_era_filter}
                ) >= {int(min_games)}
            """
        async with self.bot.pg_pool.acquire() as conn:
            records = await conn.fetch(f"""
                SELECT s.user_id, MAX(s.username) AS display_name, COUNT(*) AS crown_count
                FROM crowns s
                WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter} {era_filter}
                GROUP BY s.user_id
                {min_games_clause}
                ORDER BY crown_count DESC
                LIMIT 15
            """)
        if not records:
            await interaction.followup.send("👑 No crown data for this range.")
            return
        title = "👑 Crown Leaderboard 👑"
        if title_suffix:
            title += f" ({title_suffix})"
        if era_suffix:
            title += f" — {era_suffix}"
        if min_games:
            title += f" — ≥{int(min_games)} games"
        embed = discord.Embed(title=title, color=0xf1c40f)
        for idx, row in enumerate(records, start=1):
            embed.add_field(
                name=f"#{idx} {row['display_name']}",
                value=f"{row['crown_count']} Crowns 👑",
                inline=False
            )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))
