import re
import datetime
from db.queries import insert_score, insert_crown, insert_fail
from utils.leaderboard import generate_leaderboard_embed

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
    Parses a single manual Wordle entry like "Wordle 1414 3/6" or "Wordle 1414 X/6"
    Inserts into scores or fails accordingly.
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
            await insert_fail(conn, message.author.id, message.author.display_name, wordle_number, date)
        else:
            # record successful score
            await insert_score(conn,
                               message.author.id,
                               message.author.display_name,
                               wordle_number,
                               date,
                               attempts)

        # optional celebratory messages
        if attempts == 1:
            await message.channel.send(
                f"This rat {message.author.mention} got it in **1/6**... LOSAH CHEATED 100%!!"
            )
        elif attempts is not None:
            prev_best = await conn.fetchval("""
                SELECT MIN(attempts) FROM scores
                WHERE user_id = $1 AND attempts IS NOT NULL
            """, message.author.id)
            if prev_best is None or attempts < prev_best:
                await message.channel.send(
                    f"Flippin {message.author.mention} just beat their personal best with **{attempts}/6**. Good Job Brev 👍"
                )


async def parse_summary_message(bot, message):
    """
    Parses an official summary message from the Wordle bot:
    "Your group is on a 1 day streak! 🔥 Here are yesterday's results:
    👑 4/6: @jack195
    5/6: @ENDLESS
    X/6: @asum955"
    Records scores, fails, crowns, uncontended crowns, then posts updated leaderboard.
    """
    if "Here are yesterday's results:" not in message.content:
        return

    lines = message.content.strip().splitlines()
    date = message.created_at.date() - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    wordle_number = (date - wordle_start).days
    pattern = re.compile(r"(\d|X)/6:\s+(.*)")

    # Collect (user_id, display_name, attempts)
    results = []
    for line in lines:
        m = pattern.search(line)
        if not m:
            continue
        raw = m.group(1).upper()
        attempts = None if raw == "X" else int(raw)
        section = m.group(2)
        for user in message.mentions:
            if f"@{user.display_name}" in section or f"<@{user.id}>" in section:
                results.append((user.id, user.display_name, attempts))

    if not results:
        return

    # Determine crown winners (minimal non-None attempts)
    nonfails = [att for _, _, att in results if att is not None]
    best = min(nonfails) if nonfails else None
    crown_winners = [uid for uid, _, att in results if att == best]

    async with bot.pg_pool.acquire() as conn:
        # Insert scores or fails
        for uid, uname, att in results:
            if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", uid):
                continue
            if att is None:
                await insert_fail(conn, uid, uname, wordle_number, date)
            else:
                await insert_score(conn, uid, uname, wordle_number, date, att)

        # Insert crowns
        if best is not None:
            for uid, uname, att in results:
                if att == best:
                    await insert_crown(conn, uid, uname, wordle_number, date)

        # Insert uncontended crowns
        if len(crown_winners) == 1:
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, count)
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE
                  SET count = uncontended_crowns.count + 1
            """, crown_winners[0])

    # Post updated leaderboard
    embed = await generate_leaderboard_embed(bot)
    await message.channel.send(embed=embed)
