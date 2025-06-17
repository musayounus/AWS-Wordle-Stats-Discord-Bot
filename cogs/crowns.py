import discord
from discord import app_commands
from discord.ext import commands

class CrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    async def crowns(self, interaction: discord.Interaction):
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, COUNT(*) AS crown_count
                FROM crowns
                GROUP BY user_id
                ORDER BY crown_count DESC
                LIMIT 10
            """)
        if not rows:
            await interaction.response.send_message("👑 No crown data yet.")
            return

        desc = ""
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User ID {r['user_id']}"
            desc += f"**{i}.** 👑 {name} — `{r['crown_count']}`\n"

        embed = discord.Embed(
            title="👑 Crown Leaderboard 👑",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))