import discord
from discord.ext import commands
from config import TOKEN, INTENTS
from db.pool import create_db_pool

bot = commands.Bot(command_prefix="!", intents=INTENTS)

@bot.event
async def setup_hook():
    bot.pg_pool = await create_db_pool()
    await bot.load_extension("cogs.leaderboard")
    await bot.load_extension("cogs.crowns")
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.predictions")
    await bot.load_extension("cogs.events")

if __name__ == "__main__":
    bot.run(TOKEN)