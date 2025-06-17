import discord
from discord import app_commands
from discord.ext import commands

class UncontendedCrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="uncontended_crowns", description="Show uncontended crown leaderboard.")
    async def uncontended_crowns(self, interaction: discord.Interaction):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, count FROM uncontended_crowns ORDER BY count DESC LIMIT 10
            """)
            if not rows:
                await interaction.response.send_message("🥇 No uncontended crown data available yet.")
                return

            description = ""
            for i, row in enumerate(rows, 1):
                user = interaction.guild.get_member(row["user_id"])
                name = user.display_name if user else f"User ID {row['user_id']}"
                description += f"{i}. {name} — 🥇 {row['count']}\n"

            embed = discord.Embed(
                title="Uncontended Crowns Leaderboard",
                description=description,
                color=0xFFD700
            )
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UncontendedCrownsCog(bot))