import discord
from discord import app_commands
from discord.ext import commands
from utils.leaderboard import generate_leaderboard_embed
from utils.parsing import calculate_streak

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show Wordle leaderboard")
    @app_commands.describe(range="Filter by: week, month, or leave empty for all-time")
    async def leaderboard(self, interaction: discord.Interaction, range: str = None):
        await interaction.response.defer(thinking=True)
        embed = await generate_leaderboard_embed(
            self.bot,
            user_id=interaction.user.id,
            range=range
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="stats", description="View your Wordle stats")
    @app_commands.describe(user="Optional user to check (defaults to yourself)")
    async def stats(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        target_user = user or interaction.user

        async with self.bot.pg_pool.acquire() as conn:
            # Get stats - games_played now includes both successes and fails
            stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS games_played,
                    COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
                    MIN(attempts) FILTER (WHERE attempts IS NOT NULL) AS best_score,
                    CASE 
                        WHEN COUNT(*) FILTER (WHERE attempts IS NOT NULL) > 0 
                        THEN ROUND(AVG(attempts)::numeric, 2)
                        ELSE NULL
                    END AS avg_score,
                    MAX(date) AS last_game
                FROM scores
                WHERE user_id = $1
                AND user_id NOT IN (SELECT user_id FROM banned_users)
            """, target_user.id)

            # Get streak data (only successful attempts)
            rows = await conn.fetch("""
                SELECT wordle_number FROM scores
                WHERE user_id = $1 AND attempts IS NOT NULL
                AND user_id NOT IN (SELECT user_id FROM banned_users)
                ORDER BY wordle_number
            """, target_user.id)

        streak_count = calculate_streak([r["wordle_number"] for r in rows])

        if not stats or stats['games_played'] == 0:
            await interaction.followup.send(
                f"ℹ️ No Wordle scores found for {target_user.display_name}."
            )
            return

        embed = discord.Embed(
            title=f"📊 Wordle Stats for {target_user.display_name}",
            color=0x3498db
        )
        
        avg_score = f"{stats['avg_score']:.2f}" if stats['avg_score'] is not None else "—"
        best_score = stats['best_score'] or "—"
        
        embed.add_field(name="Best Score", value=best_score, inline=True)
        embed.add_field(name="Avg Score", value=avg_score, inline=True)
        embed.add_field(name="Fails (X/6)", value=stats['fails'], inline=True)
        embed.add_field(name="Games Played", value=stats['games_played'], inline=True)
        embed.add_field(name="Current Streak", value=streak_count, inline=True)
        embed.add_field(name="Last Played", value=stats['last_game'] or "—", inline=True)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))