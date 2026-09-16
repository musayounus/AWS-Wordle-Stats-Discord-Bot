"""Self-check for the solve distribution chart renderer.

Run: python test_distribution.py [out.png]

Passing a path also writes a sample chart there, for eyeballing the style.
"""
import sys

from cogs.distribution import render_distribution

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SAMPLE = {1: 3, 2: 41, 3: 212, 4: 318, 5: 160, 6: 64, None: 29}


SUBTITLE = "985 games · avg 4.18 · 11 players"


def test_typical():
    png = render_distribution(SAMPLE, "Solve Distribution · Q3 2026", SUBTITLE)
    assert png.startswith(PNG_SIGNATURE)


def test_missing_rows_are_zero():
    assert render_distribution({4: 5}, "Solve Distribution").startswith(PNG_SIGNATURE)


def test_only_fails():
    assert render_distribution({None: 2}, "Solve Distribution").startswith(PNG_SIGNATURE)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    if len(sys.argv) > 1:
        with open(sys.argv[1], "wb") as f:
            f.write(render_distribution(SAMPLE, "Solve Distribution · Q3 2026", SUBTITLE))
        print(f"wrote {sys.argv[1]}")
