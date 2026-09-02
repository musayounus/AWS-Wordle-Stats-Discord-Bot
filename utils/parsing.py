import re
import datetime
from zoneinfo import ZoneInfo

import config
from utils.admin_helpers import NOT_VOIDED_SQL, current_wordle_number, validate_wordle_number
from utils.leaderboard import FAIL_PENALTY
from utils import quarterly
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

        # Anchor the number on the play date, never on the last stored number.
        # The previous version chained off MAX(wordle_number), so any one-off
        # bump fed into the next day's calculation and the offset could only
        # grow — it reached +5 before the 2026-09 resync migration.
        wordle_number = tentative_wordle
        claimed = await conn.fetchrow(
            """
            SELECT group_streak FROM summary_log
            WHERE wordle_number = $1 ORDER BY posted_at LIMIT 1
            """,
            tentative_wordle,
        )
        if claimed is not None:
            # This day is already recorded, so this is a second summary. Either:
            #   * the Wordle app posting tomorrow's results late tonight, once a
            #     player in a later timezone triggers the next puzzle — the group
            #     streak continues the series, so it really is the next wordle; or
            #   * a duplicate summary source, whose group streak restarts from 1 —
            #     same day, so let its results merge into the day already recorded
            #     instead of inventing a new one.
            prev_streak = claimed["group_streak"]
            if (
                group_streak is not None
                and prev_streak is not None
                and group_streak == prev_streak + 1
            ):
                wordle_number = tentative_wordle + 1

        # Hard ceiling: a summary can never describe a puzzle that has not
        # happened yet. This is the backstop that makes unbounded drift
        # impossible even if the group-streak signal is missing or wrong.
        ceiling = current_wordle_number(local_date)
        if wordle_number > ceiling:
            wordle_number = ceiling

        date = wordle_start + datetime.timedelta(days=wordle_number)

        cache = build_cache_from_mentions(message)

        results = []
        unresolved = []
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
                    unresolved.append(token[1])
                    continue
                results.append((uid, uname, attempts))

        if unresolved:
            print(
                f"⚠️ Wordle #{wordle_number}: skipped {len(unresolved)} "
                f"unresolvable token(s): {unresolved}",
                flush=True,
            )

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

        # Snapshot current-era ranking and diff vs the latest prior snapshot,
        # so the auto-post below can show ⬆️/⬇️ arrows when ranks change.
        current_ranks = await conn.fetch(f"""
            SELECT
                s.user_id,
                MAX(s.username) AS username,
                COUNT(*) AS games_played,
                ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS avg_attempts,
                RANK() OVER (
                    ORDER BY ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) ASC NULLS LAST,
                             COUNT(*) DESC
                ) AS rank
            FROM scores s
            WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
              AND {NOT_VOIDED_SQL.format(alias='s')}
              AND s.wordle_number >= {int(config.CURRENT_ERA_START_WORDLE)}
            GROUP BY s.user_id
        """)

        prior = await conn.fetch(
            """
            SELECT user_id, rank
            FROM leaderboard_snapshots
            WHERE wordle_number = (
                SELECT MAX(wordle_number) FROM leaderboard_snapshots
                WHERE wordle_number < $1
            )
            """,
            wordle_number,
        )
        prior_by_user = {r["user_id"]: r["rank"] for r in prior}

        deltas = {}
        for r in current_ranks:
            yr = prior_by_user.get(r["user_id"])
            if yr is None:
                continue
            d = yr - r["rank"]
            if d != 0:
                deltas[r["user_id"]] = d

        if current_ranks:
            await conn.executemany(
                """
                INSERT INTO leaderboard_snapshots
                    (wordle_number, user_id, rank, avg_attempts, games_played)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (wordle_number, user_id) DO UPDATE
                  SET rank = EXCLUDED.rank,
                      avg_attempts = EXCLUDED.avg_attempts,
                      games_played = EXCLUDED.games_played
                """,
                [
                    (wordle_number, r["user_id"], r["rank"],
                     r["avg_attempts"], r["games_played"])
                    for r in current_ranks
                ],
            )

        ranks_changed = bool(deltas) and bool(prior_by_user)

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

        # First summary of a new calendar month (KSA-local) → post previous
        # month's leaderboard with the MONTHLY_MIN_GAMES floor and crown the winner.
        posted_this_month = await conn.fetchval(
            """
            SELECT 1 FROM summary_log
            WHERE message_id <> $1
              AND date_trunc('month', (posted_at AT TIME ZONE $2)::date)
                  = date_trunc('month', ($3::timestamptz AT TIME ZONE $2)::date)
            LIMIT 1
            """,
            message.id, config.WORDLE_TZ, message.created_at,
        )

        # First summary of a new calendar quarter (KSA-local) → the four
        # quarterly awards for the quarter that just ended.
        posted_this_quarter = await conn.fetchval(
            """
            SELECT 1 FROM summary_log
            WHERE message_id <> $1
              AND date_trunc('quarter', (posted_at AT TIME ZONE $2)::date)
                  = date_trunc('quarter', ($3::timestamptz AT TIME ZONE $2)::date)
            LIMIT 1
            """,
            message.id, config.WORDLE_TZ, message.created_at,
        )

        quarterly_messages = []
        if not posted_this_quarter:
            local_today = message.created_at.astimezone(ZoneInfo(config.WORDLE_TZ)).date()
            q_year, q_num = quarterly.previous_quarter(local_today)
            # Skip any quarter the era started partway through — scoring it
            # would use incomplete data.
            if quarterly.quarter_in_era(q_year, q_num):
                awards = await quarterly.compute_awards(conn, q_year, q_num)
                if awards:
                    await quarterly.record_awards(conn, q_year, q_num, awards)
                    quarterly_messages = quarterly.announcements(q_year, q_num, awards)

        prev_winner = None
        prev_year = prev_month_num = None
        if not posted_this_month:
            local_today = message.created_at.astimezone(ZoneInfo(config.WORDLE_TZ)).date()
            last_of_prev = local_today.replace(day=1) - datetime.timedelta(days=1)
            prev_year, prev_month_num = last_of_prev.year, last_of_prev.month
            # Era cutover: skip the recap for any month entirely in the legacy
            # era (April 2026 and earlier). First real monthly recap lands at
            # the start of June 2026 covering May 2026.
            if (prev_year, prev_month_num) <= (2026, 4):
                prev_year = prev_month_num = None
            else:
                prev_winner = await conn.fetchrow(
                    f"""
                    SELECT
                        s.user_id,
                        MAX(s.username) AS username,
                        ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS avg_attempts,
                        COUNT(*) AS games_played
                    FROM scores s
                    WHERE s.user_id NOT IN (SELECT user_id FROM banned_users)
                      AND {NOT_VOIDED_SQL.format(alias='s')}
                      AND s.wordle_number >= {int(config.CURRENT_ERA_START_WORDLE)}
                      AND EXTRACT(YEAR FROM s.date) = $1
                      AND EXTRACT(MONTH FROM s.date) = $2
                    GROUP BY s.user_id
                    HAVING COUNT(*) >= {int(config.MONTHLY_MIN_GAMES)}
                    ORDER BY avg_attempts ASC, games_played DESC, s.user_id ASC
                    LIMIT 1
                    """,
                    prev_year, prev_month_num,
                )
                if prev_winner is not None:
                    await conn.execute(
                        """
                        INSERT INTO monthly_winners
                            (year, month, user_id, username, avg_attempts, games_played)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (year, month) DO NOTHING
                        """,
                        prev_year, prev_month_num,
                        prev_winner["user_id"], prev_winner["username"],
                        prev_winner["avg_attempts"], prev_winner["games_played"],
                    )

    if config.TESTING_MODE:
        return

    from utils.leaderboard import generate_leaderboard_embed

    posted_deltas = False
    if ranks_changed:
        embed = await generate_leaderboard_embed(bot, deltas=deltas)
        await message.channel.send(embed=embed)
        posted_deltas = True

    if not posted_this_week and not posted_deltas:
        embed = await generate_leaderboard_embed(bot)
        await message.channel.send(embed=embed)

    if not posted_this_month and prev_winner is not None:
        month_name = datetime.date(prev_year, prev_month_num, 1).strftime("%B %Y")
        monthly_embed = await generate_leaderboard_embed(
            bot, year=prev_year, month=prev_month_num,
            min_games=config.MONTHLY_MIN_GAMES,
        )
        await message.channel.send(embed=monthly_embed)
        await message.channel.send(
            f"🏆 Congratulations to <@{prev_winner['user_id']}> for taking "
            f"**1st place in {month_name}** with an average of "
            f"**{prev_winner['avg_attempts']}** over {prev_winner['games_played']} games! 🎉"
        )

    # Quarter boundaries are also month boundaries, so these land after the
    # monthly recap on the same day.
    for text in quarterly_messages:
        await message.channel.send(text)