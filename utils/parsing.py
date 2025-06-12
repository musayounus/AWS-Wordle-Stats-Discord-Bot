# /utils/parsing.py
# This file centralizes all message parsing logic.

import re
import datetime
from db.queries import (
    is_user_banned,
    get_previous_best,
    insert_score,
    insert_crown
)
from utils.leaderboard import generate_leaderboard_embed

def calculate_streak(wordles):
    """Calculates the current streak from a sorted list of wordle numbers."""
    wordles = sorted(set(wordles))
    if not wordles:
        return 0
    # Start from the most recent game and count backwards
    # The streak is the number of consecutive days played up to the most recent day
    last_game = wordles[-1]
    streak = 1
    for i in range(len(wordles) - 2, -1, -1):
        if wordles[i] == last_game - streak:
            streak += 1
        else:
            # As soon as we find a gap, the streak is broken
            break
    return streak

def parse_mentions(user_section, mentions):
    """Extracts user IDs and names from a message segment, using mentions for accuracy."""
    found_users = []
    for user in mentions:
        # Check if the user is mentioned by their display name or their ID tag
        if f"@{user.display_name}" in user_section or f"<@{user.id}>" in user_section:
            found_users.append((user.id, user.display_name))
    return found_users

async def process_score(conn, channel, user_id, display_name, wordle_number, date, attempts):
    """A centralized function to process and insert a score, and send celebration messages."""
    is_banned = await is_user_banned(conn, user_id)
    if is_banned:
        return

    previous_best = await get_previous_best(conn, user_id)
    await insert_score(conn, user_id, display_name, wordle_number, date, attempts)

    # Celebratory messages
    if attempts == 1:
        await channel.send(f"This rat <@{user_id}> got it in **1/6**... LOSAH CHEATED 100%!!")
    elif previous_best is None or (attempts is not None and attempts < previous_best):
        await channel.send(f"Flippin <@{user_id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍")

async def parse_wordle_message(bot, message):
    """Parses a standard 'Wordle #### X/6' message."""
    content = message.content
    match = re.search(r'Wordle\s+(\d+)\s+((X|\d)\/6)', content, re.IGNORECASE)
    if not match:
        return

    wordle_number = int(match.group(1))
    raw_attempts = match.group(2).upper()
    attempts = None if raw_attempts == "X/6" else int(raw_attempts[0])

    async with bot.pg_pool.acquire() as conn:
        await process_score(conn, message.channel, message.author.id, message.author.display_name, wordle_number, message.created_at.date(), attempts)

async def parse_share_embed(bot, message):
    """Parses a '/share' command embed posted by a bot."""
    embed = message.embeds[0]
    match = re.search(r"Wordle\s+(\d+)\s+((X|\d)\/6)", embed.title if embed.title else "", re.IGNORECASE)
    if not match:
        return

    # Find the original user who triggered the /share command
    user = None
    channel = message.channel
    async for m in channel.history(limit=20, before=message.created_at, oldest_first=False):
        if not m.author.bot and "/share" in m.content.lower():
            user = m.author
            break
    if not user:
        return

    wordle_number = int(match.group(1))
    raw_attempts = match.group(2).upper()
    attempts = None if raw_attempts == "X/6" else int(raw_attempts[0])

    async with bot.pg_pool.acquire() as conn:
        await process_score(conn, channel, user.id, user.display_name, wordle_number, message.created_at.date(), attempts)

async def parse_summary_message(bot, message):
    """Parses a daily summary message with mentions."""
    summary_lines = message.content.strip().splitlines()
    date = message.created_at.date() - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    wordle_number = (date - wordle_start).days
    summary_pattern = re.compile(r"(\d|X)\/6:\s+(.*)")

    async with bot.pg_pool.acquire() as conn:
        # Process scores from summary
        for line in summary_lines:
            match = summary_pattern.search(line)
            if match:
                raw_attempt = match.group(1).upper()
                attempts = None if raw_attempt == "X" else int(raw_attempt)
                user_section = match.group(2)
                
                # Use mentions to get accurate user IDs
                for user_id, username in parse_mentions(user_section, message.mentions):
                    # We re-call process_score here but without the celebratory messages
                    # to avoid spamming the channel for every line in the summary.
                    is_banned = await is_user_banned(conn, user_id)
                    if not is_banned:
                        await insert_score(conn, user_id, username, wordle_number, date, attempts)

        # Process crowns from summary
        for line in summary_lines:
            if line.startswith("👑"):
                for user_id, username in parse_mentions(line, message.mentions):
                    await insert_crown(conn, user_id, username, wordle_number, date)

    # Auto-post leaderboard after summary is fully processed
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)