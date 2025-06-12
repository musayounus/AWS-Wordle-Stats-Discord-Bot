import discord
from discord.ext import commands

class CrownsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="crowns")
    async def crowns(self, ctx):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, count FROM crowns
                ORDER BY count DESC
                LIMIT 10
            """)

        if not rows:
            await ctx.send("No crown data available yet.")
            return

        description = ""
        for i, row in enumerate(rows, 1):
            user = ctx.guild.get_member(row["user_id"])
            name = user.display_name if user else f"User ID {row['user_id']}"
            description += f"{i}. {name} — 👑 {row['count']}\n"

        embed = discord.Embed(title="Crown Leaderboard", description=description, color=0xFFD700)
        await ctx.send(embed=embed)

    @commands.command(name="uncontended_crowns")
    async def uncontended_crowns(self, ctx):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, count FROM uncontended_crowns
                ORDER BY count DESC
                LIMIT 10
            """)

        if not rows:
            await ctx.send("No uncontended crown data available yet.")
            return

        description = ""
        for i, row in enumerate(rows, 1):
            user = ctx.guild.get_member(row["user_id"])
            name = user.display_name if user else f"User ID {row['user_id']}"
            description += f"{i}. {name} — 🥇 {row['count']}\n"

        embed = discord.Embed(title="Uncontended Crown Leaderboard", description=description, color=0x1ABC9C)
        await ctx.send(embed=embed)

# Register the cog
async def setup(bot):
    await bot.add_cog(CrownsCog(bot))