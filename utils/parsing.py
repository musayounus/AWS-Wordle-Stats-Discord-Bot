# utils/parsing.py

import re
import datetime

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
        # skip banned
        banned = await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", message.author.id)
        if banned:
            return

        # insert score or fail
        if attempts is None:
            from db.queries import insert_fail
            await insert_fail(conn, message.author.id, message.author.display_name, wordle_number, date)
        else:
            from db.queries import insert_score
            await insert_score(conn,
                               message.author.id,
                               message.author.display_name,
                               wordle_number,
                               date,
                               attempts)

        # celebrations
        if attempts == 1:
            await message.channel.send(f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!")
        else:
            prev_best = await conn.fetchval("""
                SELECT MIN(attempts) FROM scores
                WHERE user_id = $1 AND attempts IS NOT NULL
            """, message.author.id)
            if attempts and (prev_best is None or attempts < prev_best):
                await message.channel.send(
                    f"Flippin {message.author.mention} just beat their personal best with **{attempts}/6**. Good Job Brev 👍"
                )

async def parse_summary_message(bot, message):
    if "Here are yesterday's results:" not in message.content:
        return

    summary_lines = message.content.strip().splitlines()
    date = message.created_at.date() - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    wordle_number = (date - wordle_start).days
    pattern = re.compile(r"(\d|X)/6:\s+(.*)")

    results = []
    for line in summary_lines:
        m = pattern.search(line)
        if not m:
            continue
        raw = m.group(1).upper()
        attempts = None if raw == "X" else int(raw)
        section = m.group(2)
        for user in message.mentions:
            if f"@{user.display_name}" in section or f"<@{user.id}>" in section:
                results.append((user.id, user.display_name, attempts))

    # crowns (same as before)
    best = min((r[2] for r in results if r[2] is not None), default=None)
    top = [(u,i) for u,i,a in results if a == best]

    async with bot.pg_pool.acquire() as conn:
        from db.queries import insert_score, insert_crown, insert_fail

        # insert scores/fails
        for uid, uname, att in results:
            banned = await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id=$1", uid)
            if banned:
                continue
            if att is None:
                await insert_fail(conn, uid, uname, wordle_number, date)
            else:
                await insert_score(conn, uid, uname, wordle_number, date, att)

        # insert crowns
        for uid, uname, att in results:
            if att == best:
                await insert_crown(conn, uid, uname, wordle_number, date)

        # uncontended
        if len(top) == 1:
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, count)
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE
                  SET count = uncontended_crowns.count + 1
            """, top[0][0])

    from utils.leaderboard import generate_leaderboard_embed
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)