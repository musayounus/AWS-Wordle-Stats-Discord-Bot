import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# prevent duplicate runs
import psutil
def is_bot_already_running():
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid','name','cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            cmd = proc.info['cmdline']
            if proc.info['name'] and 'python' in proc.info['name'].lower() and cmd and 'bot.py' in ' '.join(cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

if is_bot_already_running():
    print("⛔ Another bot instance is already running. Exiting.")
    sys.exit(1)

# Load .env early (for TOKEN, AWS_REGION, RDS_*, etc)
load_dotenv()

# Central config
import config

# Bot instance
bot = commands.Bot(command_prefix="!", intents=config.INTENTS)

# Database pool
from db.pool import create_db_pool

@bot.event
async def setup_hook():
    # 1) Connect to RDS
    bot.pg_pool = await create_db_pool()
    print("✅ Database pool initialized.")

    # 2) Load all cogs
    COGS_LIST = [
        "cogs.admin",
        "cogs.leaderboard",
        "cogs.streaks",
        "cogs.help",
        "cogs.predictions",
        "cogs.events",
        "cogs.crowns",
        "cogs.uncontended_crowns",
        "cogs.banned_users",
        "cogs.fails",
    ]
    for cog in COGS_LIST:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed loading {cog}: {e}")

    # 3) Sync slash commands globally & to test guild
    try:
        await bot.tree.sync()
        await bot.tree.sync(guild=discord.Object(id=config.TEST_GUILD_ID))
        print("✅ Slash commands synced.")
    except Exception as e:
        print(f"⚠️ Error syncing slash commands: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_error(event_method, *args, **kwargs):
    import traceback
    print(f"❌ Unhandled error in {event_method}:\n{traceback.format_exc()}")

if __name__ == "__main__":
    try:
        bot.run(config.TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")