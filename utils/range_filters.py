import calendar
import datetime
from zoneinfo import ZoneInfo

from discord import app_commands

import config

MONTH_CHOICES = [
    app_commands.Choice(name=calendar.month_name[m], value=m) for m in range(1, 13)
]

ERA_CHOICES = [
    app_commands.Choice(name="current", value="current"),
    app_commands.Choice(name="legacy", value="legacy"),
]

SEASON_CHOICES = [
    app_commands.Choice(name="current", value="current"),
    app_commands.Choice(name="all", value="all"),
]

QUARTER_CHOICES = [
    app_commands.Choice(name=f"Q{q}", value=q) for q in range(1, 5)
]


# ── quarter arithmetic ────────────────────────────────────────────────────────
# Lives here rather than in utils.awards because utils.awards imports
# utils.leaderboard, which imports this module — putting it there would close an
# import cycle. utils.awards imports these back from here.

def quarter_of(d: datetime.date) -> int:
    return (d.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int):
    """Return (start, end) dates for a quarter; end is exclusive."""
    start = datetime.date(year, 3 * (quarter - 1) + 1, 1)
    end = (datetime.date(year + 1, 1, 1) if quarter == 4
           else datetime.date(year, 3 * quarter + 1, 1))
    return start, end


def wordle_today() -> datetime.date:
    """Today's date in WORDLE_TZ, matching how scores are dated."""
    return datetime.datetime.now(ZoneInfo(config.WORDLE_TZ)).date()


def current_season(today: datetime.date = None):
    """(year, quarter) of the season in progress, or None before seasons start.

    Returning None keeps every board at its pre-season, full-era behaviour until
    the SEASON_FIRST_* cutover, so this can ship well ahead of the start date.
    """
    if today is None:
        today = wordle_today()
    season = (today.year, quarter_of(today))
    if season < (int(config.SEASON_FIRST_YEAR), int(config.SEASON_FIRST_QUARTER)):
        return None
    return season


def build_era_filter(era="current", column="s.wordle_number"):
    """Return (sql_fragment, title_suffix) for the given era.

    current → wordle_number >= CURRENT_ERA_START_WORDLE (no title annotation)
    legacy  → wordle_number <  CURRENT_ERA_START_WORDLE (title suffix "Legacy")
    """
    cutoff = int(config.CURRENT_ERA_START_WORDLE)
    if era == "legacy":
        return f"AND {column} < {cutoff}", "Legacy"
    return f"AND {column} >= {cutoff}", None


def build_date_filter(year=None, month=None, column="s.date"):
    """Return (sql_fragment, title_suffix) for the given year/month.

    Integers are coerced and inlined — callers pass validated app_commands
    inputs so no injection risk.
    """
    if year is not None and month is not None:
        return (
            f"AND EXTRACT(YEAR FROM {column}) = {int(year)} "
            f"AND EXTRACT(MONTH FROM {column}) = {int(month)}",
            f"{calendar.month_name[int(month)]} {int(year)}",
        )
    if year is not None:
        return f"AND EXTRACT(YEAR FROM {column}) = {int(year)}", str(int(year))
    if month is not None:
        return (
            f"AND EXTRACT(MONTH FROM {column}) = {int(month)} "
            f"AND EXTRACT(YEAR FROM {column}) = EXTRACT(YEAR FROM CURRENT_DATE)",
            calendar.month_name[int(month)],
        )
    return "", None


def build_window_filter(season="current", year=None, month=None, quarter=None,
                        column="s.date", today=None):
    """Return (sql_fragment, title_suffix) for the time window of a board.

    Resolution order, most explicit first:

      quarter given      → that quarter (year defaults to the current year)
      year and/or month  → that calendar range, season ignored
      season="all"       → no window at all, the whole era
      otherwise          → the season in progress, or no window before cutover

    An explicit year/month view always wins over the season default, which is
    what keeps the monthly recap posts (which pass year and month) showing a
    full month rather than a month intersected with the current quarter.
    """
    if quarter is not None:
        y = int(year) if year is not None else (today or wordle_today()).year
        return _quarter_filter(y, int(quarter), column)

    if year is not None or month is not None:
        return build_date_filter(year=year, month=month, column=column)

    if season == "all":
        return "", "All Time"

    current = current_season(today)
    if current is None:
        return "", None
    return _quarter_filter(current[0], current[1], column)


def _quarter_filter(year: int, quarter: int, column: str):
    start, end = quarter_bounds(int(year), int(quarter))
    return (
        f"AND {column} >= DATE '{start}' AND {column} < DATE '{end}'",
        f"Q{int(quarter)} {int(year)}",
    )
