import discord
from discord import app_commands
from discord.ext import commands
from utils.leaderboard import generate_leaderboard_embed

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show Wordle leaderboard")
    @app_commands.describe(range="Filter by: week, month, or leave empty for all-time")
    async def leaderboard(self, interaction: discord.Interaction, range: str = None):
        await interaction.response.defer(thinking=True)
        embed = await generate_leaderboard_embed(self.bot, user_id=interaction.user.id, range=range)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="stats", description="View your Wordle stats")
    @app_commands.describe(user="Optional user to check (defaults to yourself)")
    async def stats(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        target_user = user or interaction.user
        async with self.bot.pg_pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT COUNT(*) FILTER (WHERE attempts IS NOT NULL) AS games_played,
                       COUNT(*) FILTER (WHERE attempts IS NULL) AS fails,
                       MIN(attempts) AS best_score,
                       ROUND(AVG(attempts)::numeric, 2) AS avg_score,
                       MAX(date) AS last_game
                FROM scores
                WHERE user_id = $1 AND user_id NOT IN (SELECT user_id FROM banned_users)
            """, target_user.id)

            rows = await conn.fetch("""
                SELECT wordle_number FROM scores
                WHERE user_id = $1 AND attempts IS NOT NULL AND user_id NOT IN (SELECT user_id FROM banned_users)
                ORDER BY wordle_number
            """, target_user.id)
            from utils.parsing import calculate_streak
            streak_count = calculate_streak([r["wordle_number"] for r in rows])

        if not stats or stats['games_played'] == 0 and stats['fails'] == 0:
            await interaction.followup.send(f"ℹ️ No Wordle scores found for {target_user.display_name}.")
            return

        embed = discord.Embed(
            title=f"📊 Wordle Stats for {target_user.display_name}",
            color=0x3498db
        )
        embed.add_field(name="Best Score", value=stats['best_score'] or "—", inline=True)
        embed.add_field(name="Avg Score", value=stats['avg_score'] or "—", inline=True)
        embed.add_field(name="Fails (X/6)", value=stats['fails'], inline=True)
        embed.add_field(name="Games Played", value=stats['games_played'], inline=True)
        embed.add_field(name="Current Streak", value=streak_count, inline=True)
        embed.add_field(name="Last Played", value=stats['last_game'] or "—", inline=True)
        await interaction.followup.send(embed=embed)

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
    await bot.add_cog(LeaderboardCog(bot))