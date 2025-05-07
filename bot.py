import os
import sys
import psutil
import discord
from discord.ext import commands
import asyncpg
import json
import re
import boto3
import datetime
import asyncio
from discord import app_commands
from dotenv import load_dotenv

TEST_GUILD_ID = 1364244767201955910

# Prevent duplicate bot instances
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

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Initialize bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# PostgreSQL connection pool
async def create_db_pool():
    session = boto3.session.Session()
    client = session.client('secretsmanager', region_name='eu-central-1')
    response = client.get_secret_value(
        SecretId='arn:aws:secretsmanager:eu-central-1:222634374532:secret:rds!db-5bb0c45b-baa5-40c4-9763-6fc3136ad726'
    )
    secret = json.loads(response['SecretString'])
    pool = await asyncpg.create_pool(
        user=secret['username'],
        password=secret['password'],
        database='postgres',
        host='wordle-db.cjywummmsd5i.eu-central-1.rds.amazonaws.com',
        port=5432,
        ssl='require',
        min_size=1,
        max_size=5,
        timeout=10
    )
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return pool

@bot.event
async def setup_hook():
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=TEST_GUILD_ID))
    bot.pg_pool = await create_db_pool()
    print("✅ Slash commands synced and DB connected.")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content

    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', content, re.IGNORECASE)
    if match:
        wordle_number = int(match.group(1))
        raw = match.group(2).upper()
        attempts = None if raw == "X" else int(raw)
        date = message.created_at.date()
        async with bot.pg_pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (username, wordle_number) DO NOTHING
                """, message.author.id, str(message.author), wordle_number, date, attempts)
                print(f"✅ Saved individual score: {message.author} - {raw}/6 for Wordle {wordle_number}")
            except Exception as e:
                print(f"⚠️ Failed to insert individual score: {e}")

    if "Here are yesterday's results:" in content:
        print("📊 Detected summary message")
        summary_lines = content.strip().splitlines()
        date = message.created_at.date()
        wordle_start = datetime.date(2021, 6, 19)
        wordle_number = (date - wordle_start).days
        print(f"📅 Calculated Wordle #{wordle_number} for summary")

        summary_pattern = re.compile(r"(\d|X)/6:\s+(.*)")
        results = []

        for line in summary_lines:
            match = summary_pattern.search(line)
            if match:
                raw_attempt = match.group(1)
                attempts = None if raw_attempt.upper() == "X" else int(raw_attempt)
                user_section = match.group(2)
                mentions = message.mentions
                if mentions:
                    for user in mentions:
                        if f"@{user.name}" in user_section or f"<@{user.id}>" in user_section:
                            results.append((user.id, str(user), attempts))
                else:
                    usernames = re.findall(r"@[^\s]+", user_section)
                    for uname in usernames:
                        results.append((None, uname, attempts))

        async with bot.pg_pool.acquire() as conn:
            for user_id, username, attempts in results:
                try:
                    await conn.execute("""
                        INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (username, wordle_number) DO NOTHING
                    """, user_id, username, wordle_number, date, attempts)
                    print(f"✅ Summary inserted: {username} - {attempts}/6")
                except Exception as e:
                    print(f"⚠️ Summary insert failed for {username}: {e}")

    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    if before.content != after.content or before.embeds != after.embeds:
        await on_message(after)

@bot.tree.command(name="leaderboard", description="Show Wordle leaderboard", guild=discord.Object(id=TEST_GUILD_ID))
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        async with bot.pg_pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT username, AVG(attempts) as avg_attempts, COUNT(*) FILTER (WHERE attempts IS NOT NULL) as games_played
                FROM scores
                WHERE attempts IS NOT NULL
                GROUP BY username
                ORDER BY avg_attempts ASC, games_played DESC
                LIMIT 10
            """)
        embed = discord.Embed(title="🏆 Wordle Leaderboard", color=0x00ff00)
        for idx, row in enumerate(records, start=1):
            embed.add_field(
                name=f"#{idx} {row['username']}",
                value=f"Avg: {row['avg_attempts']:.2f} | Games: {row['games_played']}",
                inline=False
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"❌ Leaderboard error: {e}")
        await interaction.followup.send("Error generating leaderboard.")

@bot.tree.command(name="resetleaderboard", description="Reset the Wordle leaderboard", guild=discord.Object(id=TEST_GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def resetleaderboard(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ Type `yes` within 30s to confirm reset.")
    def check(m): return m.author.id == interaction.user.id and m.content.lower() == "yes"
    try:
        await bot.wait_for("message", timeout=30.0, check=check)
        async with bot.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM scores")
        await interaction.followup.send("✅ Leaderboard reset.")
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ Reset cancelled.")
    except Exception as e:
        print(f"❌ Reset error: {e}")
        await interaction.followup.send("❌ Reset failed.")

@resetleaderboard.error
async def reset_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ You don't have permission to do that.", ephemeral=True)

bot.run(TOKEN)
