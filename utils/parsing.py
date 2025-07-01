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
    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', message.content, re.IGNORECASE)
    if not match:
        return

    wordle_number = int(match.group(1))
    raw = match.group(2).upper()
    attempts = None if raw == "X" else int(raw)
    date = message.created_at.date()

    async with bot.pg_pool.acquire() as conn:
        # Skip banned users
        if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", message.author.id):
            return

        # Always record in scores table (whether success or fail)
        await conn.execute("""
            INSERT INTO scores (user_id, username, wordle_number, date, attempts)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (username, wordle_number) DO UPDATE
            SET attempts = $5
        """, message.author.id, message.author.display_name, wordle_number, date, attempts)

        # For fails, also record in fails table
        if attempts is None:
            await conn.execute("""
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, message.author.id, message.author.display_name, wordle_number, date)
            return

        # Only check for personal best if it was a successful attempt
        previous_best = await conn.fetchval("""
            SELECT MIN(attempts) FROM scores
            WHERE user_id = $1 AND attempts IS NOT NULL AND wordle_number != $2
        """, message.author.id, wordle_number)

        # Handle 1/6 case
        if attempts == 1:
            await message.channel.send(f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!")
        elif previous_best is None or attempts < previous_best:
            await message.channel.send(
                f"Flippin {message.author.mention} just beat their personal best with **{attempts}/6**. Good Job Brev 👍"
            )

async def parse_summary_message(bot, message):
    if "Here are yesterday's results:" not in (message.content or ""):
        return

    summary_lines = message.content.strip().splitlines()
    date = message.created_at.date() - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    wordle_number = (date - wordle_start).days
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
                    if f"@{user.display_name}" in user_section or f"<@{user.id}>" in user_section:
                        results.append((user.id, user.display_name, attempts))

    # Crown tracking
    crown_users = []
    for line in summary_lines:
        if line.startswith("👑"):
            mentions = message.mentions
            if mentions:
                for user in mentions:
                    if f"@{user.display_name}" in line or f"<@{user.id}>" in line:
                        crown_users.append(user)

    async with bot.pg_pool.acquire() as conn:
        # Process all results
        for user_id, username, attempts in results:
            # Skip banned users
            if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user_id):
                continue

            # Always record in scores table
            await conn.execute("""
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (username, wordle_number) DO UPDATE
                SET attempts = $5
            """, user_id, username, wordle_number, date, attempts)

            # For fails, also record in fails table
            if attempts is None:
                await conn.execute("""
                    INSERT INTO fails (user_id, username, wordle_number, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                """, user_id, username, wordle_number, date)
            else:
                # Only check for personal best if it was a successful attempt
                previous_best = await conn.fetchval("""
                    SELECT MIN(attempts) FROM scores
                    WHERE user_id = $1 AND attempts IS NOT NULL AND wordle_number != $2
                """, user_id, wordle_number)

                # Handle 1/6 case
                if attempts == 1:
                    await message.channel.send(f"This rat <@{user_id}> got it in **1/6**... LOSAH CHEATED 100%!!")
                elif previous_best is None or attempts < previous_best:
                    await message.channel.send(
                        f"Flippin <@{user_id}> just beat their personal best with **{attempts}/6**. Good Job Brev 👍"
                    )

        # Crown processing
        for user in crown_users:
            await conn.execute("""
                INSERT INTO crowns (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
            """, user.id, user.display_name, wordle_number, date)

        # Uncontended crown processing
        if len(crown_users) == 1:
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, count)
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE SET count = uncontended_crowns.count + 1
            """, crown_users[0].id)

    # Send leaderboard update
    from utils.leaderboard import generate_leaderboard_embed
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)