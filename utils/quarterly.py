"""Quarterly award calculations.

Four awards are computed for a completed quarter and announced on the first
summary of the next one:

  average      — best (lowest) average, subject to QUARTERLY_MIN_GAMES
  uncontended  — most solo first places
  solve        — most impressive single day, relative to everyone else that day
  champion     — weighted composite across all of the above plus participation

Every query is scoped to the current era, excludes banned users, and honours
voided wordles, matching the rest of the leaderboards.
"""
import datetime

import config
from utils.admin_helpers import NOT_VOIDED_SQL, WORDLE_START
from utils.leaderboard import FAIL_PENALTY

CATEGORIES = ("average", "uncontended", "solve", "champion")


def quarter_of(d: datetime.date) -> int:
    return (d.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int):
    """Return (start, end) dates for a quarter; end is exclusive."""
    start = datetime.date(year, 3 * (quarter - 1) + 1, 1)
    end = (datetime.date(year + 1, 1, 1) if quarter == 4
           else datetime.date(year, 3 * quarter + 1, 1))
    return start, end


def previous_quarter(d: datetime.date):
    """The (year, quarter) immediately before the one containing `d`."""
    q = quarter_of(d)
    return (d.year - 1, 4) if q == 1 else (d.year, q - 1)


def era_start_date() -> datetime.date:
    return WORDLE_START + datetime.timedelta(days=int(config.CURRENT_ERA_START_WORDLE))


def quarter_in_era(year: int, quarter: int) -> bool:
    """True only if the whole quarter falls inside the current era.

    A quarter the era started partway through would be scored on incomplete
    data, so it is skipped entirely — the same reasoning that makes the monthly
    recap skip April 2026 and earlier.
    """
    start, _ = quarter_bounds(year, quarter)
    return start >= era_start_date()


_ERA = "s.wordle_number >= {cutoff}"
_NOT_BANNED = "s.user_id NOT IN (SELECT user_id FROM banned_users)"


def _scope(alias="s"):
    return (
        f"{alias}.user_id NOT IN (SELECT user_id FROM banned_users) "
        f"AND {NOT_VOIDED_SQL.format(alias=alias)} "
        f"AND {alias}.wordle_number >= {int(config.CURRENT_ERA_START_WORDLE)}"
    )


async def best_average(conn, start, end):
    """Lowest average over the quarter, subject to the games floor."""
    return await conn.fetchrow(
        f"""
        SELECT s.user_id, MAX(s.username) AS username,
               ROUND(AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric, 2) AS metric,
               COUNT(*) AS games_played
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) >= {int(config.QUARTERLY_MIN_GAMES)}
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


async def solve_of_quarter(conn, start, end):
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


def _normalise(value, low, high, invert=False):
    """Min-max to 0-100. A uniform field gives everyone 100, which is
    rank-neutral — it cannot change the ordering either way."""
    if high == low:
        return 100.0
    scaled = (value - low) / (high - low) * 100.0
    return 100.0 - scaled if invert else scaled


async def champion(conn, start, end):
    """Weighted composite across average, crowns, uncontended, solve, games."""
    base = await conn.fetch(
        f"""
        SELECT s.user_id, MAX(s.username) AS username, COUNT(*) AS games,
               AVG(COALESCE(s.attempts, {FAIL_PENALTY}))::numeric AS avg_att
        FROM scores s
        WHERE {_scope()} AND s.date >= $1 AND s.date < $2
        GROUP BY s.user_id
        HAVING COUNT(*) >= {int(config.QUARTERLY_MIN_GAMES)}
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


async def compute_awards(conn, year, quarter):
    """Return {category: record} for the quarter; categories with no winner are
    omitted so the caller can simply skip announcing them."""
    start, end = quarter_bounds(year, quarter)
    awards = {}

    avg = await best_average(conn, start, end)
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

    sol = await solve_of_quarter(conn, start, end)
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

    ch = await champion(conn, start, end)
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

    return awards


async def record_awards(conn, year, quarter, awards):
    """Persist awards. Idempotent: re-running never duplicates or overwrites."""
    for category, a in awards.items():
        await conn.execute(
            """
            INSERT INTO quarterly_winners
                (year, quarter, category, user_id, username, metric, detail, games_played)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (year, quarter, category) DO NOTHING
            """,
            year, quarter, category, a["user_id"], a["username"],
            a["metric"], a["detail"], a["games_played"],
        )


def announcements(year, quarter, awards):
    """Four message strings, in announcement order. Skips missing categories."""
    tag = f"Q{quarter} {year}"
    out = []
    if "average" in awards:
        a = awards["average"]
        out.append(
            f"📊 **Best Average — {tag}**\n"
            f"Congratulations to <@{a['user_id']}> with an average of "
            f"**{a['metric']}** over {a['games_played']} games! 🎉"
        )
    if "uncontended" in awards:
        a = awards["uncontended"]
        out.append(
            f"🥇 **Most Uncontended Crowns — {tag}**\n"
            f"Congratulations to <@{a['user_id']}> with **{a['metric']}** solo "
            f"first-place finishes! 🎉"
        )
    if "solve" in awards:
        a = awards["solve"]
        out.append(
            f"🧠 **Solve of the Quarter — {tag}**\n"
            f"<@{a['user_id']}> — {a['detail']}. That's **{a['metric']}** better "
            f"than the field. 🎉"
        )
    if "champion" in awards:
        a = awards["champion"]
        out.append(
            f"🏆 **Champion of {tag}** 🏆\n"
            f"<@{a['user_id']}> takes it overall with **{a['metric']}/100**.\n"
            f"{a['detail'].split('—', 1)[1].strip()}"
        )
    return out
