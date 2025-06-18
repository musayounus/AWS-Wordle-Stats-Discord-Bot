import re
import datetime
import discord

def calculate_streak(wordles):
    wordles = sorted(set(wordles))
    if not wordles:
        return 0
    streak = 1
    for i in range(len(wordles) - 2, -1, -1):
        if wordles[i] == wordles[i + 1] - 1:
            streak += 1
        else:
            break
    return streak

async def parse_wordle_message(bot, message):
    """
    Parses a single manual Wordle entry like "Wordle 1414 3/6" or "Wordle 1414 X/6".
    Only admins may submit; this check lives in events.py.
    """
    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', message.content, re.IGNORECASE)
    if not match:
        return

    wordle_number = int(match.group(1))
    raw = match.group(2).upper()
    attempts = None if raw == "X" else int(raw)
    date = message.created_at.date()

    async with bot.pg_pool.acquire() as conn:
        # skip banned users
        if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", message.author.id):
            return

        if attempts is None:
            # record fail
            await conn.execute("""
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, message.author.id, message.author.display_name, wordle_number, date)
        else:
            # record successful score
            await conn.execute("""
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (username, wordle_number) DO NOTHING
            """, message.author.id, message.author.display_name, wordle_number, date, attempts)

        # Celebrations
        if attempts == 1:
            await message.channel.send(
                f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!"
            )
        elif attempts is not None:
            prev_best = await conn.fetchval(
                "SELECT MIN(attempts) FROM scores WHERE user_id = $1 AND attempts IS NOT NULL",
                message.author.id
            )
            if prev_best is None or attempts < prev_best:
                await message.channel.send(
                    f"Flippin {message.author.mention} just beat their personal best with **{attempts}/6**. Good Job Brev 👍"
                )

async def parse_summary_message(bot, message):
    """
    Parses an official summary message from the Wordle bot.
    Records scores, fails, crowns, uncontended crowns, then posts updated leaderboard.
    """
    content = message.content or ""
    if "Here are yesterday's results:" not in content:
        return

    lines = content.strip().splitlines()
    date = message.created_at.date() - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    wordle_number = (date - wordle_start).days
    pattern = re.compile(r"(\d|X)/6:\s+(.*)")

    results = []   # tuples of (user_obj, attempts)

    # parse each result line
    for line in lines:
        m = pattern.search(line)
        if not m:
            continue

        raw = m.group(1).upper()
        attempts = None if raw == "X" else int(raw)
        section = m.group(2).strip()

        # Check mentions first
        for user in message.mentions:
            if f"@{user.display_name}" in section or f"<@{user.id}>" in section:
                results.append((user, attempts))
                break
        else:
            # Fallback to name matching if no mentions found
            name_match = re.search(r'@([^\s@]+)', section)
            if name_match:
                name = name_match.group(1)
                user_obj = discord.utils.find(
                    lambda u: u.display_name == name or u.name == name,
                    message.guild.members
                )
                if user_obj:
                    results.append((user_obj, attempts))

    if not results:
        return

    # determine best non-fail score for crowns
    nonfails = [att for _, att in results if att is not None]
    best = min(nonfails) if nonfails else None
    crown_winners = [u for u, att in results if att == best]

    async with bot.pg_pool.acquire() as conn:
        for user, att in results:
            if not isinstance(user, discord.Member):
                continue

            # skip banned
            if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user.id):
                continue

            # insert fail or score
            if att is None:
                await conn.execute("""
                    INSERT INTO fails (user_id, username, wordle_number, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                """, user.id, user.display_name, wordle_number, date)
            else:
                await conn.execute("""
                    INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (username, wordle_number) DO NOTHING
                """, user.id, user.display_name, wordle_number, date, att)

        # insert crowns
        if best is not None:
            for winner in crown_winners:
                if isinstance(winner, discord.Member):
                    await conn.execute("""
                        INSERT INTO crowns (user_id, username, wordle_number, date)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT DO NOTHING
                    """, winner.id, winner.display_name, wordle_number, date)

        # insert uncontended crowns
        if len(crown_winners) == 1 and isinstance(crown_winners[0], discord.Member):
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, count)
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE
                SET count = uncontended_crowns.count + 1
            """, crown_winners[0].id)

    # send updated leaderboard
    from utils.leaderboard import generate_leaderboard_embed
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)