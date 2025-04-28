import discord
from discord.ext import commands
import aiosqlite
import re
import datetime
import asyncio
from discord import app_commands
import dotenv
import os

dotenv.load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Important for reading message content
bot = commands.Bot(command_prefix="!", intents=intents)

# Sync slash commands
@bot.event
async def setup_hook():
    await bot.tree.sync()

# Initialize database
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    async with aiosqlite.connect("wordle.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            wordle_number INTEGER,
            date TEXT,
            attempts INTEGER,
            UNIQUE(user_id, wordle_number) -- Prevent duplicate entries
        )
        """)
        await db.commit()

# Listen to messages
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Default to message.author if we can't find interaction user
    target_user = message.author

    # Check if this is a response to a slash command (like /share)
    if message.interaction:
        # This is a response to a slash command - get the user who triggered it
        target_user = message.interaction.user
    elif message.reference:  # Fallback: Check if it's a reply to another message
        try:
            referenced_msg = await message.channel.fetch_message(message.reference.message_id)
            if referenced_msg.interaction:  # If the referenced message was from a slash command
                target_user = referenced_msg.interaction.user
        except discord.NotFound:
            pass

    content = message.content

    # If it's an embed (like from /share), extract content
    if message.embeds:
        embed = message.embeds[0]
        content = ""
        if embed.title:
            content += embed.title + "\n"
        if embed.description:
            content += embed.description + "\n"
        if embed.fields:
            for field in embed.fields:
                content += (field.name or "") + "\n" + (field.value or "") + "\n"

    # Debug: Print the user and content
    print("=" * 50)
    print(f"Message from: {target_user} (ID: {target_user.id})")
    print(f"Raw message content:\n{message.content}")
    print(f"Extracted content:\n{content}")
    print("=" * 50)

    # Search for Wordle pattern (e.g., "Wordle 1408 6/6")
    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', content, re.IGNORECASE)
    if match:
        wordle_number = int(match.group(1))
        attempts = match.group(2).upper()
        attempts = 7 if attempts == "X" else int(attempts)

        date = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

        # Save to database (using target_user)
        async with aiosqlite.connect("wordle.db") as db:
            try:
                await db.execute("""
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES (?, ?, ?, ?, ?)
                """, (target_user.id, str(target_user), wordle_number, date, attempts))
                await db.commit()
                print(f"✅ Saved: {target_user} | Wordle {wordle_number} | Attempts: {attempts}")
            except aiosqlite.IntegrityError:
                print(f"⚠️ Duplicate entry: {target_user} | Wordle {wordle_number}")
    else:
        print("❌ No Wordle match found in message.")

    await bot.process_commands(message)

# Listen for message edits (for /share updates)
@bot.event
async def on_message_edit(before, after):
    if before.content != after.content or before.embeds != after.embeds:
        await on_message(after)

# Slash command to view leaderboard
@bot.tree.command(name="leaderboard", description="Show the Wordle leaderboard")
async def leaderboard(interaction: discord.Interaction):
    async with aiosqlite.connect("wordle.db") as db:
        async with db.execute("""
        SELECT username, AVG(attempts) as avg_attempts, COUNT(*) as games_played
        FROM scores
        GROUP BY username
        HAVING games_played >= 1
        ORDER BY avg_attempts ASC, games_played DESC
        LIMIT 10
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await interaction.response.send_message("No scores recorded yet.")
        return

    embed = discord.Embed(
        title="🏆 Wordle Leaderboard 🏆",
        description="Top 10 players by **average attempts**",
        color=discord.Color.gold()
    )
    for idx, (username, avg_attempts, games_played) in enumerate(rows, start=1):
        embed.add_field(
            name=f"#{idx} {username}",
            value=f"**Avg Attempts:** `{avg_attempts:.2f}` • **Games Played:** `{games_played}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# Slash command to reset leaderboard (admin only)
@bot.tree.command(name="resetleaderboard", description="Reset the Wordle leaderboard (admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def resetleaderboard(interaction: discord.Interaction):
    await interaction.response.send_message(
        "⚠️ Are you sure you want to reset the leaderboard? Type `yes` within 30 seconds to confirm."
    )

    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.content.lower() == "yes"

    try:
        msg = await bot.wait_for('message', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ Reset cancelled. (No confirmation received)")
        return

    async with aiosqlite.connect("wordle.db") as db:
        await db.execute("DELETE FROM scores;")
        await db.commit()

    await interaction.followup.send("✅ Leaderboard has been reset!")

bot.run(TOKEN)
