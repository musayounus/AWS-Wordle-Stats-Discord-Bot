import discord
from discord import app_commands
from discord.ext import commands

class CrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    async def crowns(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT user_id, MAX(username) AS display_name, COUNT(*) AS crown_count
                FROM crowns
                GROUP BY user_id
                ORDER BY crown_count DESC
            """)
        if not records:
            await interaction.followup.send("👑 No crown data yet.")
            return
        embed = discord.Embed(title="👑 Crown Leaderboard 👑", color=0xf1c40f)
        for idx, row in enumerate(records, start=1):
            embed.add_field(name=f"#{idx} {row['display_name']}", value=f"{row['crown_count']} Crowns 👑", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))