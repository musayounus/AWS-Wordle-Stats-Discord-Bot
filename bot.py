import os
import sys
import io
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Fix Windows console encoding for emoji output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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

# Testing-mode hardening: admin-only slash invocations, every response
# ephemeral by default. Gets stripped entirely once TESTING_MODE is off.
if config.TESTING_MODE:
    print("🔧 TESTING_MODE active: admin-only invocations, ephemeral responses.", flush=True)

    _orig_ir_send = discord.InteractionResponse.send_message
    _orig_ir_defer = discord.InteractionResponse.defer
    _orig_wh_send = discord.Webhook.send

    async def _ir_send(self, *args, **kwargs):
        kwargs.setdefault("ephemeral", True)
        return await _orig_ir_send(self, *args, **kwargs)

    async def _ir_defer(self, *args, **kwargs):
        kwargs.setdefault("ephemeral", True)
        return await _orig_ir_defer(self, *args, **kwargs)

    async def _wh_send(self, *args, **kwargs):
        kwargs.setdefault("ephemeral", True)
        return await _orig_wh_send(self, *args, **kwargs)

    discord.InteractionResponse.send_message = _ir_send
    discord.InteractionResponse.defer = _ir_defer
    discord.Webhook.send = _wh_send

    async def _testing_mode_check(interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        if perms is not None and perms.administrator:
            return True
        try:
            await interaction.response.send_message(
                "🔧 Bot is in testing mode — admin only. Ask the server admin to disable testing mode when ready.",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            pass
        return False

    bot.tree.interaction_check = _testing_mode_check

# Database pool
from db.pool import create_db_pool

@bot.event
async def setup_hook():
    # 1) Connect to RDS
    bot.pg_pool = await create_db_pool()
    print("✅ Database pool initialized.")

    async with bot.pg_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voided_wordles (
                wordle_number INTEGER PRIMARY KEY,
                voided_at TIMESTAMPTZ DEFAULT NOW(),
                reason TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voided_user_wordles (
                user_id BIGINT NOT NULL,
                wordle_number INTEGER NOT NULL,
                voided_at TIMESTAMPTZ DEFAULT NOW(),
                reason TEXT,
                PRIMARY KEY (user_id, wordle_number)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS summary_log (
                message_id BIGINT PRIMARY KEY,
                posted_at TIMESTAMPTZ NOT NULL,
                wordle_number INTEGER NOT NULL,
                group_streak INTEGER
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_summary_log_posted_at ON summary_log (posted_at)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monthly_winners (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                username TEXT NOT NULL,
                avg_attempts NUMERIC,
                games_played INTEGER,
                recorded_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (year, month)
            )
        """)

    # 2) Load all cogs
    COGS_LIST = [
        "cogs.admin",
        "cogs.leaderboard",
        "cogs.help",
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

    # 3) Sync slash commands globally & to test guild (if TEST_GUILD_ID is set)
    try:
        await bot.tree.sync()
        if config.TEST_GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=config.TEST_GUILD_ID))
        print("✅ Slash commands synced.")
    except Exception as e:
        print(f"⚠️ Error syncing slash commands: {e}")

@tasks.loop(minutes=5)
async def heartbeat():
    print("💓 Heartbeat: bot is alive", flush=True)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if not heartbeat.is_running():
        heartbeat.start()

@bot.event
async def on_error(event_method, *args, **kwargs):
    import traceback
    print(f"❌ Unhandled error in {event_method}:\n{traceback.format_exc()}")

if __name__ == "__main__":
    try:
        bot.run(config.TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")