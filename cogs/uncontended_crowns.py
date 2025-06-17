import discord
from discord import app_commands
from discord.ext import commands

class UncontendedCrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uncontended_crowns", description="Show the uncontended crowns leaderboard.")
    async def uncontended_crowns(self, interaction: discord.Interaction):
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, count FROM uncontended_crowns ORDER BY count DESC LIMIT 10
            """)
            if not rows:
                await interaction.response.send_message("🥇 No uncontended data available yet.")
                return

            leaderboard = ""
            for i, row in enumerate(rows, 1):
                user = interaction.guild.get_member(row["user_id"])
                name = user.display_name if user else f"User ID {row['user_id']}"
                leaderboard += f"**{i}.** 🥇 {name} — `{row['count']}`\n"

            embed = discord.Embed(
                title="🥇 Uncontended Leaderboard 🥇",
                description=leaderboard,
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UncontendedCrownsCog(bot))