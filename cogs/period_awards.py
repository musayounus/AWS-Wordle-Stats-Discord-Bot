import discord
from discord import app_commands
from discord.ext import commands

from utils.awards import period_label

# Display order and label for each award category.
LABELS = {
    "champion": ("🏆", "Champion"),
    "average": ("📊", "Best Average"),
    "uncontended": ("🥇", "Most Uncontended"),
    "solve": ("🧠", "Best Solve"),
}
ORDER = ("champion", "average", "uncontended", "solve")


class PeriodAwardsCog(commands.Cog):
    """Show the four award winners of each past quarter and year."""

    def __init__(self, bot):
        self.bot = bot

    async def _render(self, interaction, period_type, title, empty_msg):
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT year, period, category, user_id, username, metric, detail
                FROM period_awards
                WHERE period_type = $1
                ORDER BY year DESC, period DESC
                """,
                period_type,
            )
        if not rows:
            await interaction.followup.send(empty_msg)
            return

        grouped = {}
        for r in rows:
            grouped.setdefault((r["year"], r["period"]), {})[r["category"]] = r

        embed = discord.Embed(title=title, color=0xF1C40F)
        # Discord caps an embed at 25 fields.
        for (year, period) in list(grouped)[:25]:
            awards = grouped[(year, period)]
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
                name=period_label(period_type, year, period),
                value="\n".join(lines) or "—",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="quarterly_champions",
        description="Show the four award winners of each past quarter",
    )
    async def quarterly_champions(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self._render(
            interaction, "quarter", "🏆 Quarterly Awards 🏆",
            "📅 No quarterly awards recorded yet — the first lands at the "
            "start of October 2026, covering Q3 2026.",
        )

    @app_commands.command(
        name="yearly_champions",
        description="Show the four award winners of each past year",
    )
    async def yearly_champions(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self._render(
            interaction, "year", "🏆 Yearly Awards 🏆",
            "📅 No yearly awards recorded yet — the first lands on "
            "1 January 2027, covering 2026.",
        )


async def setup(bot):
    await bot.add_cog(PeriodAwardsCog(bot))
