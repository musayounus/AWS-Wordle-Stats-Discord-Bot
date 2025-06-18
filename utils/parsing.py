import re
import datetime
import discord

async def parse_wordle_message(bot, message):
    """
    Parses a single manual Wordle entry like "Wordle 1414 3/6" or "Wordle 1414 X/6".
    Only admins may submit; this check lives in events.py.
    """
    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', message.content or "", re.IGNORECASE)
    if not match:
        return

    wordle_number = int(match.group(1))
    raw = match.group(2).upper()
    attempts = None if raw == "X" else int(raw)
    date = message.created_at.date()

    async with bot.pg_pool.acquire() as conn:
        # skip banned users
        if await conn.fetchval(
            "SELECT 1 FROM banned_users WHERE user_id = $1",
            message.author.id
        ):
            return

        # if it's a successful attempt, fetch previous best BEFORE inserting
        previous_best = None
        if attempts is not None:
            previous_best = await conn.fetchval(
                "SELECT MIN(attempts) FROM scores WHERE user_id = $1 AND attempts IS NOT NULL",
                message.author.id
            )

        # record the score or fail
        if attempts is None:
            await conn.execute("""
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, message.author.id, message.author.display_name, wordle_number, date)
        else:
            await conn.execute("""
                INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, message.author.id, message.author.display_name, wordle_number, date, attempts)

        # Celebrations
        if attempts == 1:
            await message.channel.send(
                f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!"
            )
        elif attempts is not None and (
                previous_best is None or attempts < previous_best
        ):
            await message.channel.send(
                f"Flippin {message.author.mention} just beat their personal best "
                f"with **{attempts}/6**. Good Job Brev 👍"
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

    # First pass: collect raw entries (user, attempts) in a dict to dedupe
    summary_map = {}
    for line in lines:
        m = pattern.search(line)
        if not m:
            continue

        raw = m.group(1).upper()
        attempts = None if raw == "X" else int(raw)
        section = m.group(2)

        # Look for a mention
        for user in message.mentions:
            if f"<@{user.id}>" in section or f"@{user.display_name}" in section:
                prev = summary_map.get(user.id)
                # If we already saw a real score, keep it; if we saw a fail but now have real, overwrite
                if prev is None or (prev is None and attempts is not None):
                    summary_map[user.id] = (user, attempts)
                break

    if not summary_map:
        return

    # Determine crown winners (best non-fail)
    nonfails = [att for _, att in summary_map.values() if att is not None]
    best_score = min(nonfails) if nonfails else None
    crown_winners = [
        user for user, att in summary_map.values() if att == best_score
    ]

    async with bot.pg_pool.acquire() as conn:
        # Insert scores/fails
        for user, attempts in summary_map.values():
            # skip banned
            if await conn.fetchval(
                "SELECT 1 FROM banned_users WHERE user_id = $1",
                user.id
            ):
                continue

            if attempts is None:
                await conn.execute("""
                    INSERT INTO fails (user_id, username, wordle_number, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                """, user.id, user.display_name, wordle_number, date)
            else:
                await conn.execute("""
                    INSERT INTO scores (user_id, username, wordle_number, date, attempts)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id, wordle_number) DO NOTHING
                """, user.id, user.display_name, wordle_number, date, attempts)

        # Insert crowns
        if best_score is not None:
            for winner in crown_winners:
                await conn.execute("""
                    INSERT INTO crowns (user_id, username, wordle_number, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                """, winner.id, winner.display_name, wordle_number, date)

        # Insert uncontended crown
        if len(crown_winners) == 1:
            winner = crown_winners[0]
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, count)
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE
                  SET count = uncontended_crowns.count + 1
            """, winner.id)

    # Finally, re‑post the updated leaderboard
    from utils.leaderboard import generate_leaderboard_embed
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)