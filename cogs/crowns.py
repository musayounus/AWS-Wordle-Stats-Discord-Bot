from discord.ext import commands
from discord import app_commands, Interaction, Embed
from db.queries import get_crowns

class CrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crowns", description="Show how many times each user placed #1 (👑)")
    async def crowns(self, interaction: Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            records = await get_crowns(conn)
        if not records:
            await interaction.followup.send("👑 No crown data yet.")
            return
        embed = Embed(title="👑 Crown Leaderboard 👑", color=0xf1c40f)
        for idx, row in enumerate(records, start=1):
            embed.add_field(name=f"#{idx} {row['display_name']}", value=f"{row['crown_count']} Crowns 👑", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CrownsCog(bot))