"""Self-check for the quarterly season window filters.

Run: python test_seasons.py

Covers the parts that are easy to get wrong: the cutover gate, and the
precedence of an explicit year/month view over the season default (which is
what keeps the monthly recap posts correct).
"""
import datetime

from utils.admin_helpers import WORDLE_START
from utils.range_filters import (
    build_window_filter,
    current_season,
    quarter_bounds,
    quarter_of,
    season_of_wordle,
    snapshot_comparable,
)

BEFORE = datetime.date(2026, 9, 12)   # Q3 2026, before seasons start
FIRST = datetime.date(2026, 10, 1)    # first day of Q4 2026
MID = datetime.date(2026, 11, 20)     # mid Q4 2026
NEXT = datetime.date(2027, 1, 5)      # Q1 2027


def test_quarter_arithmetic():
    assert quarter_of(datetime.date(2026, 1, 1)) == 1
    assert quarter_of(datetime.date(2026, 9, 30)) == 3
    assert quarter_of(FIRST) == 4
    assert quarter_bounds(2026, 4) == (datetime.date(2026, 10, 1),
                                       datetime.date(2027, 1, 1))
    assert quarter_bounds(2026, 1) == (datetime.date(2026, 1, 1),
                                       datetime.date(2026, 4, 1))


def test_gate_before_cutover():
    """Before Q4 2026 nothing changes: no season, no window, no title."""
    assert current_season(BEFORE) is None
    assert build_window_filter(today=BEFORE) == ("", None)


def test_current_season_window():
    assert current_season(FIRST) == (2026, 4)
    assert current_season(MID) == (2026, 4)
    assert current_season(NEXT) == (2027, 1)

    sql, title = build_window_filter(today=MID)
    assert title == "Q4 2026"
    assert "s.date >= DATE '2026-10-01'" in sql
    assert "s.date < DATE '2027-01-01'" in sql

    # The season rolls over on its own at the boundary - no code change needed.
    sql, title = build_window_filter(today=NEXT)
    assert title == "Q1 2027"
    assert "s.date >= DATE '2027-01-01'" in sql


def test_season_all_shows_whole_era():
    assert build_window_filter(season="all", today=MID) == ("", "All Time")


def test_explicit_year_month_beats_season():
    """The monthly recap passes year+month and must get a full month."""
    sql, title = build_window_filter(season="current", year=2026, month=11, today=MID)
    assert title == "November 2026"
    assert "EXTRACT(MONTH FROM s.date) = 11" in sql
    assert "DATE '2026-10-01'" not in sql  # not intersected with the quarter

    sql, title = build_window_filter(season="current", year=2026, today=MID)
    assert title == "2026"
    assert "EXTRACT(YEAR FROM s.date) = 2026" in sql


def test_explicit_quarter():
    sql, title = build_window_filter(quarter=1, year=2027, today=MID)
    assert title == "Q1 2027"
    assert "s.date >= DATE '2027-01-01'" in sql
    assert "s.date < DATE '2027-04-01'" in sql

    # quarter without year falls back to the current year, like month does
    sql, title = build_window_filter(quarter=2, today=MID)
    assert title == "Q2 2026"
    assert "s.date >= DATE '2026-04-01'" in sql


def test_column_is_honoured():
    sql, _ = build_window_filter(today=MID, column="f.date")
    assert "f.date >= DATE '2026-10-01'" in sql
    assert "s.date" not in sql


def _wordle_on(d: datetime.date) -> int:
    """The wordle number for a given date, inverse of wordle_date_for_number."""
    return (d - WORDLE_START).days


def test_season_of_wordle():
    assert season_of_wordle(_wordle_on(datetime.date(2026, 9, 30))) == (2026, 3)
    assert season_of_wordle(_wordle_on(FIRST)) == (2026, 4)
    assert season_of_wordle(_wordle_on(NEXT)) == (2027, 1)


def test_snapshot_comparable_uses_todays_season():
    """The gate must compare against the season actually queried.

    The snapshot query windows on *today*, but the daily summary reports
    yesterday. On 1 October the summary's wordle is still Q3, so comparing the
    snapshot to the summary's wordle would wrongly pass and show the very
    arrows this is meant to suppress.
    """
    q3_last = _wordle_on(datetime.date(2026, 9, 30))
    q4_mid = _wordle_on(MID)

    # 1 Oct: yesterday's snapshot is Q3, today's window is Q4 -> not comparable
    assert not snapshot_comparable(q3_last, today=FIRST)
    # inside a season: comparable
    assert snapshot_comparable(q4_mid, today=MID)
    # new year rolls to Q1 2027, so a Q4 snapshot is stale again
    assert not snapshot_comparable(q4_mid, today=NEXT)


def test_snapshot_comparable_is_inert_before_cutover():
    """Pre-cutover the window is era-wide, so no snapshot is ever stale.

    Without this, a quarter boundary before the cutover would silently drop a
    delta post for no reason.
    """
    q2 = _wordle_on(datetime.date(2026, 6, 15))
    assert snapshot_comparable(q2, today=BEFORE)
    assert snapshot_comparable(q2, today=datetime.date(2026, 7, 1))


def test_legacy_era_skips_the_season_window():
    """era=legacy is disjoint from every season window.

    Wordle #1777 is 2026-05-01, so legacy means dates before that, while the
    first season is Q4 2026. Applying the season default to a legacy request
    returns nothing at all.
    """
    sql, title = build_window_filter(era="legacy", today=MID)
    assert sql == ""
    assert title is None

    # an explicit range still works alongside era=legacy
    sql, title = build_window_filter(era="legacy", year=2025, today=MID)
    assert "EXTRACT(YEAR FROM s.date) = 2025" in sql
    sql, title = build_window_filter(era="legacy", quarter=1, year=2026, today=MID)
    assert "s.date >= DATE '2026-01-01'" in sql

    # current era is unaffected
    sql, _ = build_window_filter(era="current", today=MID)
    assert "2026-10-01" in sql


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll season filter checks passed.")
