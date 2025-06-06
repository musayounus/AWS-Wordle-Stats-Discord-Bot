import discord
from discord.ext import commands
import psutil
import sys
import os
from config import DISCORD_BOT_TOKEN
from db.pool import create_db_pool

TOKEN = DISCORD_BOT_TOKEN

def is_bot_already_running():
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            if ('python' in proc.info['name'].lower() and
                proc.info['cmdline'] and
                'bot.py' in ' '.join(proc.info['cmdline'])):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

if is_bot_already_running():
    print("⛔ Another bot instance is already running. Exiting.")
    sys.exit(1)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook():
    bot.pg_pool = await create_db_pool()
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.crowns")
    await bot.load_extension("cogs.leaderboard")
    await bot.load_extension("cogs.predictions")
    await bot.load_extension("cogs.events")
    print("✅ All cogs loaded and DB connected.")

bot.run(TOKEN)