from discord.ext import commands
from discord import app_commands, Interaction, Embed
from config import TEST_GUILD_ID
from db.queries import get_leaderboard, get_user_rank_row

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show Wordle leaderboard")
    @app_commands.describe(range="Filter by time range: 'week', 'month', or leave empty for all-time")
    async def leaderboard(self, interaction: Interaction, range: str = None):
        await interaction.response.defer(thinking=True)
        async with self.bot.pg_pool.acquire() as conn:
            leaderboard_rows = await get_leaderboard(conn, range)
            user_rank_row = await get_user_rank_row(conn, interaction.user.id, range)
        title_map = {
            None: "🏆 Wordle Leaderboard (All Time)",
            "week": "📅 Wordle Leaderboard (Last 7 Days)",
            "month": "🗓️ Wordle Leaderboard (This Month)"
        }
        embed = Embed(title=title_map.get(range, "🏆 Wordle Leaderboard"), color=0x00ff00)
        if not leaderboard_rows:
            embed.description = "No scores yet for this range."
        else:
            for idx, row in enumerate(leaderboard_rows, start=1):
                emoji_best = "🧠" if row['best_score'] == 1 else ""
                emoji_fail = "💀" if row['fails'] > 0 else ""
                embed.add_field(
                    name=f"#{idx} {row['username']}",
                    value=(f"Avg: {row['avg_attempts']:.2f} | Best: {row['best_score'] or '—'} {emoji_best}\n"
                           f"Games: {row['games_played']} | Fails: {row['fails']} {emoji_fail}"),
                    inline=False
                )
            if user_rank_row and user_rank_row['user_id'] not in [r['user_id'] for r in leaderboard_rows]:
                emoji_best = "🧠" if user_rank_row['best_score'] == 1 else ""
                emoji_fail = "💀" if user_rank_row['fails'] > 0 else ""
                embed.add_field(
                    name=f"⬇️ Your Rank: #{user_rank_row['rank']} {user_rank_row['username']}",
                    value=(f"Avg: {user_rank_row['avg_attempts']:.2f} | Best: {user_rank_row['best_score'] or '—'} {emoji_best}\n"
                           f"Games: {user_rank_row['games_played']} | Fails: {user_rank_row['fails']} {emoji_fail}"),
                    inline=False
                )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))