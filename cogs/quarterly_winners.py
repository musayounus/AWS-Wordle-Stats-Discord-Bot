import discord
from discord import app_commands
from discord.ext import commands

# Display order and labels for the four awards, keyed by the `category` column.
LABELS = {
    "champion": ("🏆", "Champion"),
    "average": ("📊", "Best Average"),
    "uncontended": ("🥇", "Most Uncontended"),
    "solve": ("🧠", "Solve of the Quarter"),
}
ORDER = ("champion", "average", "uncontended", "solve")


class QuarterlyWinnersCog(commands.Cog):
    """Show the four per-quarter award winners (auto-recorded each quarter)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="quarterly_champions",
        description="Show the four award winners of each past quarter",
    )
    async def quarterly_winners(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT year, quarter, category, user_id, username, metric, detail
                FROM quarterly_winners
                ORDER BY year DESC, quarter DESC
                """
            )
        if not rows:
            await interaction.followup.send(
                "📅 No quarterly awards recorded yet — the first lands at the "
                "start of January 2027, covering Q4 2026."
            )
            return

        by_quarter = {}
        for r in rows:
            by_quarter.setdefault((r["year"], r["quarter"]), {})[r["category"]] = r

        embed = discord.Embed(title="🏆 Quarterly Awards 🏆", color=0xF1C40F)
        # Discord caps an embed at 25 fields.
        for (year, quarter) in list(by_quarter)[:25]:
            awards = by_quarter[(year, quarter)]
            lines = []
            for category in ORDER:
                r = awards.get(category)
                if r is None:
                    continue
                emoji, label = LABELS.get(category, ("•", category.title()))
                member = (
                    interaction.guild.get_member(r["user_id"])
                    if interaction.guild else None
                )
                display = member.display_name if member else r["username"]
                lines.append(f"{emoji} **{label}:** {display} — {r['detail']}")
            embed.add_field(
                name=f"Q{quarter} {year}",
                value="\n".join(lines) or "—",
                inline=False,
            )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(QuarterlyWinnersCog(bot))
