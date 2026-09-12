"""Self-check for the single award-field table.

Run: python test_awards_fields.py

The announcement embed and the /quarterly_champions listing both walk FIELDS.
The point of one table is that a new award cannot appear in one surface and go
missing from the other, and that the compact labels stay compact.
"""
from utils.awards import COMPACT_FIELDS, FIELDS

EXPECTED = (
    "champion", "average", "uncontended", "solve", "aces",
    "metronome", "improved", "streak", "best_month", "hardest",
)


def test_categories_and_order():
    assert tuple(f[0] for f in FIELDS) == EXPECTED


def test_compact_view_matches_the_table():
    """Same categories, same order, same emoji - only the label differs."""
    assert tuple(c for c, _, _ in COMPACT_FIELDS) == EXPECTED
    assert [e for _, e, _ in COMPACT_FIELDS] == [f[1] for f in FIELDS]
    assert len(COMPACT_FIELDS) == len(FIELDS)


def test_every_row_is_complete():
    for row in FIELDS:
        category, emoji, quarter, year, compact = row
        assert category and emoji and quarter and year and compact
        assert len(row) == 5


def test_announcement_labels_are_period_specific():
    by_cat = {f[0]: f for f in FIELDS}
    assert by_cat["solve"][2] == "Solve of the Quarter"
    assert by_cat["solve"][3] == "Solve of the Year"
    assert by_cat["hardest"][2] == "Hardest Wordle of the Quarter"
    assert by_cat["hardest"][3] == "Hardest Wordle of the Year"


def test_compact_labels_stay_shorter():
    """The listing shows up to 25 periods per embed, so these must not grow
    into the spelled-out announcement forms."""
    for category, _, quarter, _, compact in FIELDS:
        assert len(compact) <= len(quarter), category
    assert dict((c, l) for c, _, l in COMPACT_FIELDS)["solve"] == "Best Solve"
    assert dict((c, l) for c, _, l in COMPACT_FIELDS)["hardest"] == "Hardest Wordle"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll award field checks passed.")
