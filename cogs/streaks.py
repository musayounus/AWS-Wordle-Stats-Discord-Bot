import discord
from discord import app_commands
from discord.ext import commands
from utils.parsing import calculate_streak

class StreaksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="streak", description="Show your current Wordle streak")
    async def streak(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT wordle_number
                FROM scores
                WHERE user_id = $1 AND attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
                ORDER BY wordle_number
            """, interaction.user.id)
        wordles = [r["wordle_number"] for r in rows]
        streak_count = calculate_streak(wordles)
        await interaction.followup.send(f"🔥 Your current streak is **{streak_count}** Wordles in a row.")

    @app_commands.command(name="streaks", description="Top 10 Wordle streaks")
    async def streaks(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            users = await conn.fetch("""
                SELECT DISTINCT user_id, username
                FROM scores
                WHERE attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
            """)
            results = []
            for user in users:
                wordles = await conn.fetch("""
                    SELECT wordle_number
                    FROM scores
                    WHERE user_id = $1 AND attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
                    ORDER BY wordle_number
                """, user["user_id"])
                wordle_nums = [r["wordle_number"] for r in wordles]
                streak_count = calculate_streak(wordle_nums)
                if streak_count > 0:
                    results.append((user["username"], streak_count))
        results.sort(key=lambda x: x[1], reverse=True)
        embed = discord.Embed(title="🔥 Top Streaks 🔥", color=0xff9900)
        for idx, (user, streak_count) in enumerate(results[:10], start=1):
            embed.add_field(name=f"#{idx} {user}", value=f"{streak_count} in a row", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(StreaksCog(bot))