"""Self-check for the quarterly season window filters.

Run: python test_seasons.py

Covers the parts that are easy to get wrong: the cutover gate, and the
precedence of an explicit year/month view over the season default (which is
what keeps the monthly recap posts correct).
"""
import datetime

from utils.admin_helpers import WORDLE_START
from utils.range_filters import (
    build_era_filter,
    build_window_filter,
    current_season,
    quarter_bounds,
    quarter_of,
    season_for_wordle,
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


def test_season_for_wordle_gates_on_the_cutover():
    assert season_for_wordle(_wordle_on(datetime.date(2026, 6, 15))) is None   # Q2, pre
    assert season_for_wordle(_wordle_on(datetime.date(2026, 9, 30))) is None   # Q3, pre
    assert season_for_wordle(_wordle_on(FIRST)) == (2026, 4)
    assert season_for_wordle(_wordle_on(NEXT)) == (2027, 1)


def test_summary_window_uses_the_summarys_season_not_today():
    """The 1 October case: the summary covers 30 September, which is Q3.

    Windowing on today would rank the brand-new empty Q4 and post it beside
    Q3 results. Q3 is before the cutover, so the correct answer here is no
    window at all - and from 1 January onward it is the completed quarter.
    """
    sep30 = _wordle_on(datetime.date(2026, 9, 30))
    assert season_for_wordle(sep30) is None          # -> season="all", no window

    # 1 Jan 2027: summary covers 31 Dec 2026, which is Q4 2026, not Q1 2027.
    dec31 = _wordle_on(datetime.date(2026, 12, 31))
    season = season_for_wordle(dec31)
    assert season == (2026, 4)
    sql, title = build_window_filter(quarter=season[1], year=season[0])
    assert title == "Q4 2026"
    assert "s.date >= DATE '2026-10-01'" in sql
    assert "2027-01-01" in sql   # exclusive upper bound


def test_snapshot_comparable_against_the_passed_season():
    """The gate compares against whatever window the caller queried."""
    q4_mid = _wordle_on(MID)
    q3_last = _wordle_on(datetime.date(2026, 9, 30))

    assert snapshot_comparable(q4_mid, (2026, 4))
    assert not snapshot_comparable(q3_last, (2026, 4))
    assert not snapshot_comparable(q4_mid, (2027, 1))
    # None means no season window applied, so anything is comparable
    assert snapshot_comparable(q3_last, None)
    assert snapshot_comparable(q4_mid, None)


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


def test_combined_era_drops_the_era_predicate():
    """era=combined counts both eras, so it filters on neither."""
    sql, title = build_era_filter("combined")
    assert sql == ""
    assert title == "Combined Eras"

    # the other two still carry their cutoff predicate
    assert "<" in build_era_filter("legacy")[0]
    assert ">=" in build_era_filter("current")[0]


def test_combined_era_skips_the_season_window():
    """Combined means the whole history, not the quarter in progress."""
    sql, title = build_window_filter(era="combined", today=MID)
    assert sql == ""
    assert title is None

    # an explicit range still narrows it
    sql, _ = build_window_filter(era="combined", quarter=4, year=2026, today=MID)
    assert "s.date >= DATE '2026-10-01'" in sql


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll season filter checks passed.")
