import datetime
import discord
from discord import app_commands
from discord.ext import commands


class MonthlyWinnersCog(commands.Cog):
    """Show the per-month 1st-place winners (auto-recorded each month)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="monthly_winners",
        description="Show the 1st-place winner of each past month",
    )
    async def monthly_winners(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT year, month, user_id, username, avg_attempts, games_played
                FROM monthly_winners
                ORDER BY year DESC, month DESC
                """
            )
        if not rows:
            await interaction.followup.send(
                "📅 No monthly winners recorded yet — first one lands at the start of next month."
            )
            return

        embed = discord.Embed(title="🏆 Monthly Winners 🏆", color=0xf1c40f)
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
