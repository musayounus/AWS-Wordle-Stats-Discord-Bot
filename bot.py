import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio

# For debugging: prevent duplicate bot instances (optional)
import psutil
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

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Configurable (set your IDs here or import from config.py)
TEST_GUILD_ID = 1364244767201955910
COGS_LIST = [
    "cogs.admin",
    "cogs.leaderboard",
    "cogs.streaks",
    "cogs.help",
    "cogs.predictions",
    "cogs.events",
    "cogs.crowns",
    "cogs.uncontended_crowns",  # newly added
]

# Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

# Bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# DB Pool setup (using asyncpg & boto3 in db/pool.py)
from db.pool import create_db_pool

@bot.event
async def setup_hook():
    # Create PostgreSQL connection pool and attach to bot
    bot.pg_pool = await create_db_pool()
    print("✅ Database pool initialized.")

    # Load all cogs
    for cog in COGS_LIST:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")

    # Sync slash commands (globally and to test guild)
    try:
        await bot.tree.sync()
        await bot.tree.sync(guild=discord.Object(id=TEST_GUILD_ID))
        print("✅ Slash commands synced (global & test guild).")
    except Exception as e:
        print(f"⚠️ Error syncing slash commands: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# Error handler for uncaught exceptions
@bot.event
async def on_error(event_method, *args, **kwargs):
    import traceback
    print(f"❌ Unhandled error in {event_method}:", traceback.format_exc())

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")