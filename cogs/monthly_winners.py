import datetime
import discord
from discord import app_commands
from discord.ext import commands

from utils.range_filters import ERA_CHOICES

# Era boundary for monthly_winners: rows from May 2026 onward = current era,
# anything before = legacy. Keyed on (year, month) since the table doesn't
# carry wordle_number.
ERA_BOUNDARY_YEAR = 2026
ERA_BOUNDARY_MONTH = 5


class MonthlyWinnersCog(commands.Cog):
    """Show the per-month 1st-place winners (auto-recorded each month)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="monthly_champions",
        description="Show the 1st-place winner of each past month",
    )
    @app_commands.describe(
        era="current (May 2026 onward, default) or legacy (before May 2026)",
    )
    @app_commands.choices(era=ERA_CHOICES)
    async def monthly_winners(
        self,
        interaction: discord.Interaction,
        era: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        era_value = era.value if era else "current"
        if era_value == "legacy":
            era_clause = f"WHERE (year, month) < ({ERA_BOUNDARY_YEAR}, {ERA_BOUNDARY_MONTH})"
            empty_msg = "📅 No legacy monthly winners recorded."
            title_suffix = " — Legacy"
        else:
            era_clause = f"WHERE (year, month) >= ({ERA_BOUNDARY_YEAR}, {ERA_BOUNDARY_MONTH})"
            empty_msg = (
                "📅 No monthly winners recorded yet — first one lands at the start of June 2026."
            )
            title_suffix = ""

        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT year, month, user_id, username, avg_attempts, games_played
                FROM monthly_winners
                {era_clause}
                ORDER BY year DESC, month DESC
                """
            )
        if not rows:
            await interaction.followup.send(empty_msg)
            return

        embed = discord.Embed(title=f"🏆 Monthly Winners 🏆{title_suffix}", color=0xf1c40f)
        for r in rows[:25]:
            month_name = datetime.date(r["year"], r["month"], 1).strftime("%B %Y")
            member = interaction.guild.get_member(r["user_id"]) if interaction.guild else None
            display = member.display_name if member else r["username"]
            embed.add_field(
                name=month_name,
                value=(
                    f"👑 {display}\n"
                    f"Avg: {r['avg_attempts']} | Games: {r['games_played']}"
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MonthlyWinnersCog(bot))
