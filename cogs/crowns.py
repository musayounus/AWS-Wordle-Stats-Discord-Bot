import discord
from discord import app_commands
from discord.ext import commands
from utils.admin_helpers import NOT_VOIDED_SQL
from utils.range_filters import MONTH_CHOICES, RANGE_CHOICES, build_date_filter

class CrownsCog(commands.Cog):
    """Crown leaderboard showing first-place finishes."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    @app_commands.describe(
        range="Relative window: week, month, year (ignored if year/month are set)",
        year="Specific year to filter by",
        month="Specific month (uses current year if year is omitted)",
    )
    @app_commands.choices(range=RANGE_CHOICES, month=MONTH_CHOICES)
    async def crowns(
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
            records = await conn.fetch(f"""
                SELECT user_id, MAX(username) AS display_name, COUNT(*) AS crown_count
                FROM crowns s
                WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                  {date_filter}
                GROUP BY user_id
                ORDER BY crown_count DESC
                LIMIT 15
            """)
        if not records:
            await interaction.followup.send("👑 No crown data for this range.")
            return
        title = "👑 Crown Leaderboard 👑"
        if title_suffix:
            title += f" ({title_suffix})"
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
