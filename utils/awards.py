"""Period award calculations, shared by the quarterly and yearly awards.

Four awards are computed over a completed period and announced on the first
summary of the next one:

  average      — best (lowest) average, subject to a games floor
  uncontended  — most solo first places
  solve        — most impressive single day, relative to everyone else that day
  champion     — weighted composite across all of the above plus participation

Every query is scoped to the current era, excludes banned users, and honours
voided wordles, matching the rest of the leaderboards.
"""
import datetime
import math

import discord

import config
from utils.admin_helpers import NOT_VOIDED_SQL
from utils.leaderboard import FAIL_PENALTY

CATEGORIES = (
    "champion", "average", "uncontended", "solve",
    "metronome", "improved", "streak", "unbroken", "best_month", "hardest",
)

# Announcement order, with the label for each period type.
_FIELDS = (
    ("champion", "🏆", "Champion", "Champion"),
    ("average", "📊", "Best Average", "Best Average"),
    ("uncontended", "🥇", "Most Uncontended Crowns", "Most Uncontended Crowns"),
    ("solve", "🧠", "Solve of the Quarter", "Solve of the Year"),
    ("metronome", "🎯", "The Metronome", "The Metronome"),
    ("improved", "📈", "Most Improved", "Most Improved"),
    ("streak", "🔥", "Longest Streak", "Longest Streak"),
    ("unbroken", "🛡️", "Unbroken", "Unbroken"),
    ("best_month", "📅", "Best Month of the Quarter", "Best Month of the Year"),
    ("hardest", "💀", "Hardest Wordle of the Quarter", "Hardest Wordle of the Year"),
)

# The hardest-Wordle award describes a day, not a player, so it stores no user.
GROUP_CATEGORIES = ("hardest",)


# ── period arithmetic ─────────────────────────────────────────────────────────

def quarter_of(d: datetime.date) -> int:
    return (d.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int):
    """Return (start, end) dates for a quarter; end is exclusive."""
    start = datetime.date(year, 3 * (quarter - 1) + 1, 1)
    end = (datetime.date(year + 1, 1, 1) if quarter == 4
           else datetime.date(year, 3 * quarter + 1, 1))
    return start, end


def year_bounds(year: int):
    """Return (start, end) dates for a calendar year; end is exclusive."""
    return datetime.date(year, 1, 1), datetime.date(year + 1, 1, 1)


def previous_quarter(d: datetime.date):
    """The (year, quarter) immediately before the one containing `d`."""
    q = quarter_of(d)
    return (d.year - 1, 4) if q == 1 else (d.year, q - 1)


def previous_year(d: datetime.date) -> int:
    return d.year - 1


def quarter_eligible(year: int, quarter: int) -> bool:
    """Awards start at QUARTERLY_FIRST_* and run every quarter after.

    No upper bound, so all four quarters fire every year from then on. Each is
    announced on the first day of the following quarter, which puts a Q4
    announcement in the next calendar year.
    """
    return (year, quarter) >= (
        config.QUARTERLY_FIRST_YEAR,
        config.QUARTERLY_FIRST_QUARTER,
    )


def year_eligible(year: int) -> bool:
    return year >= config.YEARLY_FIRST_YEAR


def _scope(alias="s"):
    return (
        f"{alias}.user_id NOT IN (SELECT user_id FROM banned_users) "
        f"AND {NOT_VOIDED_SQL.format(alias=alias)} "
        f"AND {alias}.wordle_number >= {int(config.CURRENT_ERA_START_WORDLE)}"
    )


async def best_average(conn, start, end, min_games):
    """Lowest average over the period, subject to the games floor."""
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS metric,
               COUNT(*) AS games_played
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) >= {int(min_games)}
        ORDER BY metric ASC, games_played DESC, s.user_id ASC
        LIMIT 1
        """,
        start, end,
    )


async def most_uncontended(conn, start, end):
    """Most solo first places. No games floor — the count is the achievement."""
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               COUNT(DISTINCT s.wordle_number) AS metric,
               (SELECT COUNT(*) FROM scores sc
                WHERE sc.user_id = s.user_id AND sc.date >= $1 AND sc.date < $2
                  AND {_scope('sc')}) AS games_played
        FROM uncontended_crowns s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        ORDER BY metric DESC, games_played DESC, s.user_id ASC
        LIMIT 1
        """,
        start, end,
    )


# Per-day delta of a player against everyone else who played that day.
# X/6 counts as FAIL_PENALTY so a day of failures makes a low score shine.
_SOLVE_CTE = f"""
    WITH day AS (
        SELECT s.wordle_number, s.user_id, s.username, s.date, s.attempts,
               COALESCE(s.attempts, {FAIL_PENALTY})::numeric AS eff
        FROM scores s
        WHERE {{scope}} AND s.date >= $1 AND s.date < $2
    ), agg AS (
        SELECT wordle_number, SUM(eff) AS total, COUNT(*) AS players
        FROM day GROUP BY wordle_number
    ), rated AS (
        SELECT day.user_id, day.username, day.date, day.wordle_number, day.attempts,
               agg.players - 1 AS others,
               (agg.total - day.eff) / NULLIF(agg.players - 1, 0) AS others_avg,
               ((agg.total - day.eff) / NULLIF(agg.players - 1, 0)) - day.eff AS delta
        FROM day JOIN agg USING (wordle_number)
        WHERE agg.players - 1 >= {{min_others}}
    )
"""


def _solve_cte():
    return _SOLVE_CTE.format(scope=_scope(), min_others=int(config.SOLVE_MIN_OTHERS))


async def best_solve(conn, start, end):
    """The single most impressive day, measured against that day's field."""
    return await conn.fetchrow(
        _solve_cte() + """
        SELECT user_id, username, date, wordle_number, attempts, others,
               ROUND(others_avg, 2) AS others_avg,
               ROUND(delta, 2) AS metric
        FROM rated
        ORDER BY delta DESC, attempts ASC NULLS LAST, others DESC, date ASC, user_id ASC
        LIMIT 1
        """,
        start, end,
    )


async def metronome(conn, start, end, min_games):
    """Lowest spread of scores — never a disaster round.

    Population stddev, not sample, so a player is measured on the games they
    actually played rather than as a sample of some larger set.
    """
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               ROUND(STDDEV_POP(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS metric,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS avg_att,
               COUNT(*) AS games_played
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) >= {int(min_games)}
        ORDER BY metric ASC, avg_att ASC, games_played DESC, s.user_id ASC
        LIMIT 1
        """,
        start, end,
    )


async def most_improved(conn, start, end, min_games):
    """Biggest drop in average from the first half of the period to the second.

    Each half needs its own floor, otherwise a player with two games in the
    first half and a good second half wins on noise.
    """
    midpoint = start + datetime.timedelta(days=(end - start).days // 2)
    half_floor = max(5, int(min_games) // 3)
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))
                     FILTER (WHERE s.date < $3)::numeric, 2) AS first_half,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))
                     FILTER (WHERE s.date >= $3)::numeric, 2) AS second_half,
               COUNT(*) AS games_played,
               ROUND((AVG(COALESCE(s.attempts, {FAIL_PENALTY})) FILTER (WHERE s.date < $3)
                    - AVG(COALESCE(s.attempts, {FAIL_PENALTY})) FILTER (WHERE s.date >= $3)
                     )::numeric, 2) AS metric
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) FILTER (WHERE s.date < $3) >= {half_floor}
           AND COUNT(*) FILTER (WHERE s.date >= $3) >= {half_floor}
        ORDER BY metric DESC NULLS LAST, second_half ASC, s.user_id ASC
        LIMIT 1
        """,
        start, end, midpoint,
    )


async def unbroken(conn, start, end):
    """Played every single day the group played. Often nobody qualifies."""
    return await conn.fetchrow(
        f"""
        WITH days AS (
            SELECT COUNT(DISTINCT s.wordle_number) AS total FROM scores s
            WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        )
        SELECT s.user_id, MAX(s.username) AS username,
               COUNT(DISTINCT s.wordle_number) AS metric,
               COUNT(*) AS games_played,
               (SELECT total FROM days) AS total_days
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(DISTINCT s.wordle_number) = (SELECT total FROM days)
        ORDER BY s.user_id ASC
        LIMIT 1
        """,
        start, end,
    )


def _longest_run(numbers, voided):
    """Longest run of consecutive wordles, treating voided days as bridgeable
    rather than streak-breaking — matching calculate_streak's rule."""
    nums = sorted(set(numbers))
    if not nums:
        return 0
    best = run = 1
    for prev, nxt in zip(nums, nums[1:]):
        if set(range(prev + 1, nxt)) <= voided:
            run += 1
        else:
            run = 1
        best = max(best, run)
    return best


async def longest_streak(conn, start, end):
    """Longest unbroken run of days played inside the window."""
    rows = await conn.fetch(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               array_agg(DISTINCT s.wordle_number) AS wordles
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        """,
        start, end,
    )
    if not rows:
        return None
    global_voided = {
        r["wordle_number"]
        for r in await conn.fetch("SELECT wordle_number FROM voided_wordles")
    }
    best = None
    for r in rows:
        user_voided = {
            v["wordle_number"]
            for v in await conn.fetch(
                "SELECT wordle_number FROM voided_user_wordles WHERE user_id = $1",
                r["user_id"],
            )
        }
        run = _longest_run(r["wordles"], global_voided | user_voided)
        key = (run, -r["user_id"])
        if best is None or key > best[0]:
            best = (key, {"user_id": r["user_id"], "username": r["username"],
                          "metric": run, "games_played": len(r["wordles"])})
    return best[1] if best else None


async def best_month(conn, start, end):
    """The single best calendar month by average inside the period."""
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               EXTRACT(YEAR FROM s.date)::int AS yr,
               EXTRACT(MONTH FROM s.date)::int AS mon,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS metric,
               COUNT(*) AS games_played
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id, yr, mon
        HAVING COUNT(*) >= {int(config.MONTHLY_MIN_GAMES)}
        ORDER BY metric ASC, games_played DESC, s.user_id ASC
        LIMIT 1
        """,
        start, end,
    )


async def hardest_wordle(conn, start, end):
    """The day the group collectively struggled most. Not a player award."""
    return await conn.fetchrow(
        f"""
        SELECT s.wordle_number, MIN(s.date) AS date,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS metric,
               COUNT(*) AS players,
               COUNT(*) FILTER (WHERE s.attempts IS NULL) AS fails
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.wordle_number
        HAVING COUNT(*) >= {int(config.SOLVE_MIN_OTHERS) + 1}
        ORDER BY metric DESC, fails DESC, players DESC, s.wordle_number ASC
        LIMIT 1
        """,
        start, end,
    )


def _normalise(value, low, high, invert=False):
    """Min-max to 0-100. A uniform field gives everyone 100, which is
    rank-neutral — it cannot change the ordering either way."""
    if high == low:
        return 100.0
    scaled = (value - low) / (high - low) * 100.0
    return 100.0 - scaled if invert else scaled


async def champion(conn, start, end, min_games):
    """Weighted composite across average, crowns, uncontended, solve, games."""
    base = await conn.fetch(
        f"""
        SELECT s.user_id, MAX(s.username) AS username, COUNT(*) AS games,
               AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric AS avg_att
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) >= {int(min_games)}
        """,
        start, end,
    )
    if not base:
        return None

    crowns = {
        r["user_id"]: r["n"]
        for r in await conn.fetch(
            f"""SELECT s.user_id, COUNT(DISTINCT s.wordle_number) AS n FROM crowns s
                WHERE {_scope()} AND s.date >= $1 AND s.date < $2
                GROUP BY s.user_id""",
            start, end,
        )
    }
    uncons = {
        r["user_id"]: r["n"]
        for r in await conn.fetch(
            f"""SELECT s.user_id, COUNT(DISTINCT s.wordle_number) AS n
                FROM uncontended_crowns s
                WHERE {_scope()} AND s.date >= $1 AND s.date < $2
                GROUP BY s.user_id""",
            start, end,
        )
    }
    solves = {
        r["user_id"]: float(r["best"])
        for r in await conn.fetch(
            _solve_cte() + """
            SELECT user_id, MAX(delta) AS best FROM rated GROUP BY user_id
            """,
            start, end,
        )
        if r["best"] is not None
    }

    field = [
        {
            "user_id": r["user_id"],
            "username": r["username"],
            "games": int(r["games"]),
            "avg": float(r["avg_att"]),
            "crowns": int(crowns.get(r["user_id"], 0)),
            "uncons": int(uncons.get(r["user_id"], 0)),
            "solve": solves.get(r["user_id"], 0.0),
        }
        for r in base
    ]

    keys = ("avg", "crowns", "uncons", "solve", "games")
    low = {k: min(p[k] for p in field) for k in keys}
    high = {k: max(p[k] for p in field) for k in keys}
    w = config.CHAMPION_WEIGHTS

    for p in field:
        parts = {
            "avg": _normalise(p["avg"], low["avg"], high["avg"], invert=True),
            "crowns": _normalise(p["crowns"], low["crowns"], high["crowns"]),
            "uncons": _normalise(p["uncons"], low["uncons"], high["uncons"]),
            "solve": _normalise(p["solve"], low["solve"], high["solve"]),
            "games": _normalise(p["games"], low["games"], high["games"]),
        }
        p["score"] = round(sum(parts[k] * w[k] / 100 for k in keys), 1)

    field.sort(key=lambda p: (-p["score"], p["avg"], -p["games"], p["user_id"]))
    return field[0]


async def available_days(conn, start, end):
    """Distinct wordle days with scores in the window, era-scoped.

    Used to size the yearly floor: year windows vary (2026 is era-scoped to
    1 May-31 Dec, later years are full) so a fixed number cannot serve both.
    Deriving from real days also absorbs any day the group missed.
    """
    return await conn.fetchval(
        f"""
        SELECT COUNT(DISTINCT s.wordle_number) FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        """,
        start, end,
    ) or 0


async def yearly_min_games(conn, start, end):
    """Games floor for a year: YEARLY_ATTENDANCE_FRACTION of the days available."""
    return math.ceil(await available_days(conn, start, end)
                     * float(config.YEARLY_ATTENDANCE_FRACTION))


async def compute_awards(conn, start, end, min_games):
    """Return {category: record} for the window; categories with no winner are
    omitted so the caller can simply skip announcing them."""
    awards = {}

    avg = await best_average(conn, start, end, min_games)
    if avg is not None:
        awards["average"] = {
            "user_id": avg["user_id"], "username": avg["username"],
            "metric": avg["metric"], "games_played": avg["games_played"],
            "detail": f"{avg['metric']} average over {avg['games_played']} games",
        }

    unc = await most_uncontended(conn, start, end)
    if unc is not None:
        awards["uncontended"] = {
            "user_id": unc["user_id"], "username": unc["username"],
            "metric": unc["metric"], "games_played": unc["games_played"],
            "detail": f"{unc['metric']} uncontended crowns",
        }

    sol = await best_solve(conn, start, end)
    if sol is not None:
        shown = sol["attempts"] if sol["attempts"] is not None else "X"
        awards["solve"] = {
            "user_id": sol["user_id"], "username": sol["username"],
            "metric": sol["metric"], "games_played": None,
            "detail": (
                f"{shown}/6 on Wordle #{sol['wordle_number']} ({sol['date']}) "
                f"while {sol['others']} others averaged {sol['others_avg']}"
            ),
        }

    ch = await champion(conn, start, end, min_games)
    if ch is not None:
        awards["champion"] = {
            "user_id": ch["user_id"], "username": ch["username"],
            "metric": ch["score"], "games_played": ch["games"],
            "detail": (
                f"{ch['score']}/100 — {ch['avg']:.2f} avg, {ch['crowns']} crowns, "
                f"{ch['uncons']} uncontended, best solve +{ch['solve']:.2f}, "
                f"{ch['games']} games"
            ),
        }

    met = await metronome(conn, start, end, min_games)
    if met is not None:
        awards["metronome"] = {
            "user_id": met["user_id"], "username": met["username"],
            "metric": met["metric"], "games_played": met["games_played"],
            "detail": (f"spread of {met['metric']} around a {met['avg_att']} average "
                       f"over {met['games_played']} games"),
        }

    imp = await most_improved(conn, start, end, min_games)
    if imp is not None and imp["metric"] is not None and imp["metric"] > 0:
        awards["improved"] = {
            "user_id": imp["user_id"], "username": imp["username"],
            "metric": imp["metric"], "games_played": imp["games_played"],
            "detail": (f"{imp['first_half']} → {imp['second_half']}, "
                       f"an improvement of {imp['metric']}"),
        }

    st = await longest_streak(conn, start, end)
    if st is not None:
        awards["streak"] = {
            "user_id": st["user_id"], "username": st["username"],
            "metric": st["metric"], "games_played": st["games_played"],
            "detail": f"{st['metric']} days in a row",
        }

    unb = await unbroken(conn, start, end)
    if unb is not None:
        awards["unbroken"] = {
            "user_id": unb["user_id"], "username": unb["username"],
            "metric": unb["metric"], "games_played": unb["games_played"],
            "detail": f"played all {unb['total_days']} days — never missed one",
        }

    bm = await best_month(conn, start, end)
    if bm is not None:
        month_name = datetime.date(bm["yr"], bm["mon"], 1).strftime("%B")
        awards["best_month"] = {
            "user_id": bm["user_id"], "username": bm["username"],
            "metric": bm["metric"], "games_played": bm["games_played"],
            "detail": (f"{bm['metric']} average in {month_name} "
                       f"over {bm['games_played']} games"),
        }

    hard = await hardest_wordle(conn, start, end)
    if hard is not None:
        awards["hardest"] = {
            "user_id": None, "username": None,
            "metric": hard["metric"], "games_played": hard["players"],
            "detail": (f"Wordle #{hard['wordle_number']} ({hard['date']}) — the group "
                       f"averaged {hard['metric']} with {hard['fails']} fails "
                       f"across {hard['players']} players"),
        }

    return awards


async def record_awards(conn, period_type, year, period, awards):
    """Persist awards. Idempotent: re-running never duplicates or overwrites.

    `period` is the quarter number, or 0 for a whole year.
    """
    for category, a in awards.items():
        await conn.execute(
            """
            INSERT INTO period_awards
                (period_type, year, period, category, user_id, username,
                 metric, detail, games_played)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (period_type, year, period, category) DO NOTHING
            """,
            period_type, year, period, category, a["user_id"], a["username"],
            a["metric"], a["detail"], a["games_played"],
        )


def period_label(period_type, year, period):
    return f"Q{period} {year}" if period_type == "quarter" else str(year)


def award_embed(period_type, year, period, awards):
    """One embed carrying all four awards. Returns None if nothing qualified."""
    if not awards:
        return None
    label = period_label(period_type, year, period)
    embed = discord.Embed(
        title=f"🏆 {label} Awards 🏆",
        description=f"Congratulations to the winners of {label}!",
        color=0xF1C40F,
    )
    for category, emoji, quarter_name, year_name in _FIELDS:
        a = awards.get(category)
        if a is None:
            continue
        name = quarter_name if period_type == "quarter" else year_name
        if category == "champion":
            value = (f"<@{a['user_id']}> — **{a['metric']}/100**\n"
                     f"{a['detail'].split('—', 1)[1].strip()}")
        elif category == "average":
            value = (f"<@{a['user_id']}> — **{a['metric']}** "
                     f"over {a['games_played']} games")
        elif category == "uncontended":
            value = f"<@{a['user_id']}> — **{a['metric']}** solo first places"
        elif category == "solve":
            value = (f"<@{a['user_id']}> — {a['detail']}\n"
                     f"**{a['metric']}** better than the field")
        elif category == "streak":
            value = f"<@{a['user_id']}> — **{a['metric']}** days in a row"
        elif category == "unbroken":
            value = f"<@{a['user_id']}> — {a['detail']}"
        elif category == "hardest":
            # No player: this award describes the day itself.
            value = a["detail"]
        else:
            value = f"<@{a['user_id']}> — {a['detail']}"
        embed.add_field(name=f"{emoji} {name}", value=value, inline=False)
    return embed
