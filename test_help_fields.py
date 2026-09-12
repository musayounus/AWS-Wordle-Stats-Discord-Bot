"""Self-check for /help field chunking.

Run: python test_help_fields.py

The command list is generated and grows with every new command. A single embed
field over Discord's 1024-char cap fails the whole /help call, so the split is
the part worth pinning.
"""
from cogs.help import FIELD_LIMIT, add_lines_field


class FakeEmbed:
    def __init__(self):
        self.fields = []

    def add_field(self, name, value, inline=False):
        self.fields.append((name, value))


def test_short_list_is_one_field():
    e = FakeEmbed()
    add_lines_field(e, "Commands", ["/a – x", "/b – y"])
    assert len(e.fields) == 1
    assert e.fields[0][0] == "Commands"
    assert e.fields[0][1] == "/a – x\n/b – y"


def test_long_list_splits_and_every_field_fits():
    lines = [f"/command_{i} [year] [month] [season] [quarter] – does a thing" for i in range(40)]
    e = FakeEmbed()
    add_lines_field(e, "Commands", lines)

    assert len(e.fields) > 1, "40 commands should not fit in one field"
    for name, value in e.fields:
        assert len(value) <= FIELD_LIMIT, f"field of {len(value)} exceeds {FIELD_LIMIT}"
    # only the first field carries the heading
    assert e.fields[0][0] == "Commands"
    assert all(n == "​" for n, _ in e.fields[1:])
    # nothing dropped
    assert sum(v.count("/command_") for _, v in e.fields) == 40


def test_footer_is_kept():
    e = FakeEmbed()
    add_lines_field(e, "Commands", ["/a – x"], footer="*note*")
    assert "*note*" in "".join(v for _, v in e.fields)


def test_empty_list_adds_nothing():
    e = FakeEmbed()
    add_lines_field(e, "Commands", [])
    assert e.fields == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll /help field checks passed.")
