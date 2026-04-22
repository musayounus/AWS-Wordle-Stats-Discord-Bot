import discord
from discord import app_commands
from discord.ext import commands
from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import MONTH_CHOICES, RANGE_CHOICES, build_date_filter

class UncontendedCrownsCog(commands.Cog):
    """Leaderboard for solo first-place (uncontended) crowns."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uncontended", description="Show the uncontended crowns leaderboard.")
    @app_commands.describe(
        range="Relative window: week, month, year (ignored if year/month are set)",
        year="Specific year to filter by",
        month="Specific month (uses current year if year is omitted)",
    )
    @app_commands.choices(range=RANGE_CHOICES, month=MONTH_CHOICES)
    async def uncontended_crowns(
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
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT user_id, MAX(username) AS username, COUNT(*) AS count
                FROM uncontended_crowns s
                WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter}
                GROUP BY user_id
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
            embed = discord.Embed(
                title=title,
                description=leaderboard,
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UncontendedCrownsCog(bot))
