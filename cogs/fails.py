import discord
from discord import app_commands
from discord.ext import commands

class FailsCog(commands.Cog):
    """Track and show Wordle fails (X/6)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="fails_leaderboard",
        description="Show the Wordle fails leaderboard (who's missed Wordle most)"
    )
    async def fails_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id,
                       MAX(username) AS display_name,
                       COUNT(*) AS fail_count
                FROM fails
                WHERE user_id NOT IN (SELECT user_id FROM banned_users)
                GROUP BY user_id
                ORDER BY fail_count DESC
                LIMIT 10
            """)
        if not rows:
            await interaction.followup.send("💀 No fails recorded yet.")
            return

        embed = discord.Embed(
            title="💀 Wordle Fails Leaderboard 💀",
            color=0xff0000
        )
        for idx, r in enumerate(rows, start=1):
            embed.add_field(
                name=f"#{idx} {r['display_name']}",
                value=f"{r['fail_count']} Fails 🤣",
                inline=False
            )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(FailsCog(bot))