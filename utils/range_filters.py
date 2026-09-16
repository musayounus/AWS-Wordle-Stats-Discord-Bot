import calendar
import datetime

from discord import app_commands

import config
from utils.admin_helpers import wordle_date_for_number, wordle_today

MONTH_CHOICES = [
    app_commands.Choice(name=calendar.month_name[m], value=m) for m in range(1, 13)
]

ERA_CHOICES = [
    app_commands.Choice(name="current", value="current"),
    app_commands.Choice(name="legacy", value="legacy"),
    app_commands.Choice(name="combined", value="combined"),
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


def season_of_wordle(wordle_number: int):
    """(year, quarter) the given wordle number falls in."""
    d = wordle_date_for_number(int(wordle_number))
    return d.year, quarter_of(d)


def season_for_wordle(wordle_number: int):
    """(year, quarter) for a wordle, or None if it predates the cutover.

    A daily summary reports *yesterday*, so anything scoped to a summary must be
    windowed on that wordle's season rather than on today. On 1 October the
    summary covers 30 September, which still belongs to Q3.
    """
    season = season_of_wordle(wordle_number)
    if season < (config.SEASON_FIRST_YEAR, config.SEASON_FIRST_QUARTER):
        return None
    return season


def snapshot_comparable(prior_wordle: int, season) -> bool:
    """True when a prior snapshot was ranked over `season`, the window in use.

    `season` is whatever the caller actually queried, passed in rather than
    recomputed, so the window and this gate cannot disagree. None means no
    season window applied, in which case every snapshot is comparable.
    """
    if season is None:
        return True
    return season_of_wordle(prior_wordle) == tuple(season)


def current_season(today: datetime.date = None):
    """(year, quarter) of the season in progress, or None before seasons start.

    Returning None keeps every board at its pre-season, full-era behaviour until
    the SEASON_FIRST_* cutover, so this can ship well ahead of the start date.
    """
    if today is None:
        today = wordle_today()
    season = (today.year, quarter_of(today))
    if season < (config.SEASON_FIRST_YEAR, config.SEASON_FIRST_QUARTER):
        return None
    return season


def build_era_filter(era="current", column="s.wordle_number"):
    """Return (sql_fragment, title_suffix) for the given era.

    current  → wordle_number >= CURRENT_ERA_START_WORDLE (no title annotation)
    legacy   → wordle_number <  CURRENT_ERA_START_WORDLE (title suffix "Legacy")
    combined → no era predicate at all, so both eras count together
    """
    cutoff = int(config.CURRENT_ERA_START_WORDLE)
    if era == "legacy":
        return f"AND {column} < {cutoff}", "Legacy"
    if era == "combined":
        return "", "Combined Eras"
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
                        column="s.date", today=None, era="current"):
    """Return (sql_fragment, title_suffix) for the time window of a board.

    Most explicit wins:
      quarter            → that quarter (year defaults to the current year)
      year and/or month  → that calendar range, season ignored
      season="all"       → the whole era
      era≠"current"      → no season window; see below
      otherwise          → the season in progress, or nothing before cutover

    The year/month rule is load-bearing: the monthly recap passes both, so it
    must get a whole month, not a month intersected with the current quarter.
    `month` is ignored when `quarter` is given — quarter is the coarser window
    and wins outright.

    The era rule is equally load-bearing. Legacy means wordle_number below
    CURRENT_ERA_START_WORDLE, i.e. #1777 = 2026-05-01 and earlier, while the
    first season is Q4 2026. Those predicates are disjoint, so applying the
    season default to a legacy request returns nothing at all. The same skip
    suits era=combined, whose whole point is the full history rather than one
    quarter of it. An explicit year/month/quarter still works with either.
    """
    if quarter is not None:
        y = int(year) if year is not None else (today or wordle_today()).year
        q = int(quarter)
    elif year is not None or month is not None:
        return build_date_filter(year=year, month=month, column=column)
    elif season == "all":
        return "", "All Time"
    elif era != "current":
        return "", None
    else:
        current = current_season(today)
        if current is None:
            return "", None
        y, q = current

    start, end = quarter_bounds(y, q)
    return (
        f"AND {column} >= DATE '{start}' AND {column} < DATE '{end}'",
        f"Q{q} {y}",
    )


def window_kwargs(*, season, year, month, quarter):
    """Unwrap the app_commands Choice objects a board receives into
    build_window_filter kwargs. Same four params on every seasonal board.

    Keyword-only: month and quarter are both Choice[int], so a transposed
    positional call would be silently wrong."""
    return dict(
        season=season.value if season else "current",
        year=year,
        month=month.value if month else None,
        quarter=quarter.value if quarter else None,
    )
