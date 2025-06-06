import datetime
from discord.ext import commands, tasks
from discord import Embed
from config import PREDICTION_CHANNEL_ID, PREDICTION_TIME_HOUR
from db.queries import get_user_stats_for_predictions

class PredictionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_prediction_post.start()

    @tasks.loop(time=datetime.time(hour=PREDICTION_TIME_HOUR, tzinfo=datetime.timezone.utc))
    async def daily_prediction_post(self):
        channel = self.bot.get_channel(PREDICTION_CHANNEL_ID)
        if not channel:
            print("⚠️ Prediction channel could not be found.")
            return
        async with self.bot.pg_pool.acquire() as conn:
            user_stats = await get_user_stats_for_predictions(conn)
        if not user_stats:
            await channel.send("📉 No user data available for predictions.")
            return
        embed = Embed(
            title="🔮 Daily Wordle Predictions",
            description=f"Predictions based on past performance (as of {datetime.date.today()}):",
            color=0x9b59b6
        )
        for stat in user_stats:
            embed.add_field(
                name=stat['username'],
                value=f"Predicted score: **{stat['avg_score']:.2f}** over {stat['games_played']} games",
                inline=False
            )
        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PredictionsCog(bot))