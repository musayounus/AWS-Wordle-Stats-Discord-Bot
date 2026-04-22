import discord
from discord import app_commands
from discord.ext import commands
from utils.admin_helpers import NOT_VOIDED_SQL

class CrownsCog(commands.Cog):
    """Crown leaderboard showing first-place finishes."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    async def crowns(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            records = await conn.fetch(f"""
                SELECT user_id, MAX(username) AS display_name, COUNT(*) AS crown_count
                FROM crowns s
                WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                GROUP BY user_id
                ORDER BY crown_count DESC
                LIMIT 15
            """)
        if not records:
            await interaction.followup.send("👑 No crown data yet.")
            return
        embed = discord.Embed(title="👑 Crown Leaderboard 👑", color=0xf1c40f)
        for idx, row in enumerate(records, start=1):
            embed.add_field(
                name=f"#{idx} {row['display_name']}", 
                value=f"{row['crown_count']} Crowns 👑", 
                inline=False
            )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))