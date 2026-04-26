import re
import datetime
from zoneinfo import ZoneInfo

import config
from utils.admin_helpers import current_wordle_number, validate_wordle_number
from utils.user_resolver import (
    build_cache_from_mentions,
    extract_user_tokens,
    resolve_user,
)


def calculate_streak(wordles, current_wordle=None, voided=None):
    """Count consecutive Wordles played up to current_wordle.

    `voided` is a set of wordle numbers that should be skipped entirely —
    they neither break a streak nor count toward one. Covers both globally
    voided wordles and per-user voids.
    """
    if current_wordle is None:
        current_wordle = current_wordle_number()
    voided = voided or set()
    played = {w for w in wordles if w <= current_wordle and w not in voided}
    if not played:
        return 0

    # effective_current = largest non-voided wordle ≤ current_wordle.
    effective_current = current_wordle
    while effective_current > 0 and effective_current in voided:
        effective_current -= 1
    if effective_current <= 0:
        return 0

    # Find the most recent played wordle (skipping voids doesn't matter —
    # played set already excludes voids). Streak is live only if it's
    # effective_current or the day before (after skipping voids).
    latest_played = max(played)
    day_before = effective_current - 1
    while day_before > 0 and day_before in voided:
        day_before -= 1
    if latest_played < day_before:
        return 0

    # Walk backwards from latest_played, counting played days and skipping
    # voided numbers (they don't break the chain).
    streak = 0
    cursor = latest_played
    while cursor > 0 and cursor in played:
        streak += 1
        cursor -= 1
        while cursor > 0 and cursor in voided:
            cursor -= 1
    return streak


def _get_effective_user(message):
    """For bot-authored slash-command results (e.g., Wordle APP /share),
    return the invoking user from interaction metadata. Otherwise the author.
    """
    if not message.author.bot:
        return message.author
    meta = getattr(message, "interaction_metadata", None) or getattr(message, "interaction", None)
    user = getattr(meta, "user", None) if meta is not None else None
    if user is None:
        return message.author
    if message.guild is not None:
        member = message.guild.get_member(user.id)
        if member is not None:
            return member
    return user


def extract_message_text(message):
    """Collect a message's displayable text across plain content, embed
    title/description, and Components V2 trees (Container > Section/TextDisplay).
    Needed because Components V2 messages (e.g., Wordle APP /share) leave
    `message.content` empty and carry text inside nested components.
    """
    parts = []
    if message.content:
        parts.append(message.content)
    for e in message.embeds:
        if e.title:
            parts.append(e.title)
        if e.description:
            parts.append(e.description)

    def _walk(c):
        content = getattr(c, "content", None)
        if isinstance(content, str) and content:
            parts.append(content)
        for attr in ("children", "components"):
            sub = getattr(c, attr, None)
            if isinstance(sub, (list, tuple)):
                for s in sub:
                    _walk(s)
        accessory = getattr(c, "accessory", None)
        if accessory is not None:
            _walk(accessory)

    for c in getattr(message, "components", None) or []:
        _walk(c)
    return "\n".join(parts)


async def parse_wordle_message(bot, message):
    raw_content = extract_message_text(message)
    match = re.search(r'Wordle\s+(\d+)\s+(\d|X)/6', raw_content, re.IGNORECASE)
    if not match:
        return

    wordle_number = int(match.group(1))
    err = validate_wordle_number(wordle_number)
    if err:
        print(f"[parse_wordle_message] rejected wn={wordle_number} from {message.author}: {err}", flush=True)
        return
    raw = match.group(2).upper()
    attempts = None if raw == "X" else int(raw)
    date = message.created_at.date()
    user = _get_effective_user(message)

    async with bot.pg_pool.acquire() as conn:
        # Skip banned users
        if await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user.id):
            return

        # Always record in scores table (whether success or fail)
        await conn.execute("""
            INSERT INTO scores (user_id, username, wordle_number, date, attempts)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (username, wordle_number) DO UPDATE
            SET attempts = $5
        """, user.id, user.display_name, wordle_number, date, attempts)

        # For fails, also record in fails table
        if attempts is None:
            await conn.execute("""
                INSERT INTO fails (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, user.id, user.display_name, wordle_number, date)
            return

        # Success: remove any stale fail row for this (user, wordle) so fails stays in sync
        await conn.execute(
            "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
            user.id, wordle_number,
        )

        # Only check for personal best if it was a successful attempt
        previous_best = await conn.fetchval("""
            SELECT MIN(attempts) FROM scores
            WHERE user_id = $1 AND attempts IS NOT NULL AND wordle_number != $2
        """, user.id, wordle_number)

        # Handle 1/6 case
        if not config.TESTING_MODE:
            if attempts == 1:
                await message.channel.send(f"This person {user.mention} got it in **1/6**... You didn't cheat now, did you?..")
            elif previous_best is None or attempts < previous_best:
                await message.channel.send(
                    f"{user.mention} just beat their personal best with **{attempts}/6**. Good Job 👍"
                )

async def parse_summary_message(bot, message):
    if "Here are yesterday's results:" not in (message.content or ""):
        return
    # Only accept summaries from the official Wordle Discord app — ignore
    # anyone else posting the same header text (admin tests, copy-paste, etc).
    if message.author.id != config.OFFICIAL_WORDLE_BOT_ID:
        return

    summary_lines = message.content.strip().splitlines()
    local_date = message.created_at.astimezone(ZoneInfo(config.WORDLE_TZ)).date()
    date = local_date - datetime.timedelta(days=1)
    wordle_start = datetime.date(2021, 6, 19)
    tentative_wordle = (date - wordle_start).days
    summary_pattern = re.compile(r"(\d|X)/6:\s+(.*)")

    streak_match = re.search(r"(\d+)\s*day streak", message.content)
    group_streak = int(streak_match.group(1)) if streak_match else None

    async with bot.pg_pool.acquire() as conn:
        # Idempotency: if we've already processed this message, skip entirely.
        existing = await conn.fetchval(
            "SELECT wordle_number FROM summary_log WHERE message_id = $1",
            message.id,
        )
        if existing is not None:
            return

        # Chain: if another summary was posted before this one and already
        # claimed the tentative wordle, advance by one. Resolves two-summaries-
        # in-one-day when a traveling user triggers the next wordle early.
        last_wordle = await conn.fetchval(
            "SELECT MAX(wordle_number) FROM summary_log WHERE posted_at < $1",
            message.created_at,
        )
        if last_wordle is not None and tentative_wordle <= last_wordle:
            wordle_number = last_wordle + 1
            date = wordle_start + datetime.timedelta(days=wordle_number)
        else:
            wordle_number = tentative_wordle

        cache = build_cache_from_mentions(message)

        results = []
        for line in summary_lines:
            match = summary_pattern.search(line)
            if not match:
                continue
            raw_attempt = match.group(1)
            attempts = None if raw_attempt.upper() == "X" else int(raw_attempt)
            user_section = match.group(2)
            for token in extract_user_tokens(user_section):
                uid, uname = await resolve_user(
                    message.guild, token, cache=cache, conn=conn
                )
                if uid is None:
                    continue
                results.append((uid, uname, attempts))

        crown_users = []
        for line in summary_lines:
            if line.startswith("👑"):
                for token in extract_user_tokens(line):
                    uid, uname = await resolve_user(
                        message.guild, token, cache=cache, conn=conn
                    )
                    if uid is None:
                        continue
                    crown_users.append((uid, uname))

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
                # Success: remove any stale fail row so fails stays in sync with scores
                await conn.execute(
                    "DELETE FROM fails WHERE user_id = $1 AND wordle_number = $2",
                    user_id, wordle_number,
                )
                # Only check for personal best if it was a successful attempt
                previous_best = await conn.fetchval("""
                    SELECT MIN(attempts) FROM scores
                    WHERE user_id = $1 AND attempts IS NOT NULL AND wordle_number != $2
                """, user_id, wordle_number)

                # Handle 1/6 case
                if not config.TESTING_MODE:
                    if attempts == 1:
                        await message.channel.send(f"This person <@{user_id}> got it in **1/6**... You didn't cheat now, did you?..")
                    elif previous_best is None or attempts < previous_best:
                        await message.channel.send(
                            f"<@{user_id}> just beat their personal best with **{attempts}/6**. Good Job 👍"
                        )

        # Crown processing
        for uid, uname in crown_users:
            await conn.execute("""
                INSERT INTO crowns (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
            """, uid, uname, wordle_number, date)

        # Uncontended crown processing
        if len(crown_users) == 1:
            solo_id, solo_name = crown_users[0]
            await conn.execute("""
                INSERT INTO uncontended_crowns (user_id, username, wordle_number, date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, wordle_number) DO NOTHING
            """, solo_id, solo_name, wordle_number, date)

        await conn.execute(
            """
            INSERT INTO summary_log (message_id, posted_at, wordle_number, group_streak)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message.id, message.created_at, wordle_number, group_streak,
        )

        # Post the all-time leaderboard only on the first summary of each ISO
        # week (KSA-local), so the daily repost doesn't spam the channel.
        posted_this_week = await conn.fetchval(
            """
            SELECT 1 FROM summary_log
            WHERE message_id <> $1
              AND date_trunc('week', (posted_at AT TIME ZONE $2)::date)
                  = date_trunc('week', ($3::timestamptz AT TIME ZONE $2)::date)
            LIMIT 1
            """,
            message.id, config.WORDLE_TZ, message.created_at,
        )

    if not config.TESTING_MODE and not posted_this_week:
        from utils.leaderboard import generate_leaderboard_embed
        embed = await generate_leaderboard_embed(bot)
        await message.channel.send(embed=embed)