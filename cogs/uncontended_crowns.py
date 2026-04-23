import discord
from discord import app_commands
from discord.ext import commands
from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import MONTH_CHOICES, build_date_filter

class UncontendedCrownsCog(commands.Cog):
    """Leaderboard for solo first-place (uncontended) crowns."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uncontended", description="Show the uncontended crowns leaderboard.")
    @app_commands.describe(
        year="Specific year to filter by",
        month="Specific month (uses current year if year is omitted)",
        min_games="Only include users with at least this many games in the window",
    )
    @app_commands.choices(month=MONTH_CHOICES)
    async def uncontended_crowns(
        self,
        interaction: discord.Interaction,
        year: app_commands.Range[int, 2021, 2100] = None,
        month: app_commands.Choice[int] = None,
        min_games: app_commands.Range[int, 1, 10000] = None,
    ):
        await interaction.response.defer(thinking=True)
        date_filter, title_suffix = build_date_filter(
            year=year,
            month=month.value if month else None,
        )
        scores_date_filter, _ = build_date_filter(
            year=year,
            month=month.value if month else None,
            column="sc.date",
        )
        min_games_clause = ""
        if min_games:
            min_games_clause = f"""
                HAVING (
                    SELECT COUNT(*) FROM scores sc
                    WHERE sc.user_id = s.user_id
                      AND sc.user_id NOT IN (SELECT user_id FROM banned_users)
                      AND {NOT_VOIDED_SQL.format(alias='sc')}
                      {scores_date_filter}
                ) >= {int(min_games)}
            """
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT s.user_id, MAX(s.username) AS username, COUNT(*) AS count
                FROM uncontended_crowns s
                WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter}
                GROUP BY s.user_id
                {min_games_clause}
                ORDER BY count DESC
                LIMIT 15
            """)

            if not rows:
                await interaction.followup.send("🥇 No uncontended data for this range.")
                return

            leaderboard = ""
            for i, row in enumerate(rows, 1):
                user = interaction.guild.get_member(row["user_id"])
                name = user.display_name if user else row["username"] or f"User ID {row['user_id']}"
                leaderboard += f"**{i}.** 🥇 {name} — `{row['count']}`\n"

            title = "🥇 Uncontended Leaderboard 🥇"
            if title_suffix:
                title += f" ({title_suffix})"
            if min_games:
                title += f" — ≥{int(min_games)} games"
            embed = discord.Embed(
                title=title,
                description=leaderboard,
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UncontendedCrownsCog(bot))
