import discord
from discord.ext import commands
from discord import app_commands

class BannedUsersCog(commands.Cog):
    """Anyone can run this to see who’s banned."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="banned_users",
        description="List all users currently banned from the Wordle leaderboard"
    )
    async def banned_users(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, username FROM banned_users ORDER BY username")
        if not rows:
            await interaction.followup.send("🚫 No users are currently banned.")
            return

        text = "\n".join(f"- {r['username']} (`{r['user_id']}`)" for r in rows)
        embed = discord.Embed(
            title="🚫 Banned Users",
            description=text,
            color=0x992d22
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BannedUsersCog(bot))