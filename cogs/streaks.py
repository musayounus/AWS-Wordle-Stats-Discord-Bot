import discord
from discord import app_commands
from discord.ext import commands
from utils.parsing import calculate_streak
from utils.admin_helpers import NOT_VOIDED_SQL, load_voided_set

class StreaksCog(commands.Cog):
    """Commands for viewing individual and top streaks."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="streak", description="Show your current Wordle streak")
    async def streak(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT wordle_number
                FROM scores s
                WHERE s.user_id = $1 AND s.attempts IS NOT NULL
                  AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
                ORDER BY wordle_number
            """, interaction.user.id)
            voided = await load_voided_set(conn, interaction.user.id)
        wordles = [r["wordle_number"] for r in rows]
        streak_count = calculate_streak(wordles, voided=voided)
        await interaction.followup.send(f"🔥 Your current streak is **{streak_count}** Wordles in a row.")

    @app_commands.command(name="streaks", description="Top 15 Wordle streaks")
    async def streaks(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            users = await conn.fetch(f"""
                SELECT DISTINCT user_id, username
                FROM scores s
                WHERE s.attempts IS NOT NULL
                  AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                  AND {NOT_VOIDED_SQL.format(alias='s')}
            """)
            global_voided_rows = await conn.fetch("SELECT wordle_number FROM voided_wordles")
            global_voided = {r["wordle_number"] for r in global_voided_rows}
            results = []
            for user in users:
                wordles = await conn.fetch(f"""
                    SELECT wordle_number
                    FROM scores s
                    WHERE s.user_id = $1 AND s.attempts IS NOT NULL
                      AND s.user_id NOT IN (SELECT user_id FROM banned_users)
                      AND {NOT_VOIDED_SQL.format(alias='s')}
                    ORDER BY wordle_number
                """, user["user_id"])
                user_voided_rows = await conn.fetch(
                    "SELECT wordle_number FROM voided_user_wordles WHERE user_id = $1",
                    user["user_id"],
                )
                voided = global_voided | {r["wordle_number"] for r in user_voided_rows}
                wordle_nums = [r["wordle_number"] for r in wordles]
                streak_count = calculate_streak(wordle_nums, voided=voided)
                if streak_count > 0:
                    results.append((user["username"], streak_count))
        results.sort(key=lambda x: x[1], reverse=True)
        embed = discord.Embed(title="🔥 Top Streaks 🔥", color=0xff9900)
        for idx, (user, streak_count) in enumerate(results[:15], start=1):
            embed.add_field(name=f"#{idx} {user}", value=f"{streak_count} in a row", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(StreaksCog(bot))
