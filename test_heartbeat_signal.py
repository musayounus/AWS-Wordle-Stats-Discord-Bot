"""Self-check: the heartbeat must not claim life when the database is down.

Run: python test_heartbeat_signal.py

CloudWatch's wordle-bot-heartbeat metric filter matches the literal word
"Heartbeat" in any log line and feeds the wordle-bot-no-logs alarm. If the failure
branch ever prints that word, the alarm goes blind to a dead database again — which
is how the September 2026 outage stayed hidden for nine days.

Source-level on purpose: importing bot.py would start a Discord client.
"""
import ast
import io

SIGNAL = "Heartbeat"


def _heartbeat_fn():
    tree = ast.parse(io.open("bot.py", encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "heartbeat":
            return node
    raise AssertionError("no heartbeat() in bot.py")


def _printed_strings(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print":
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.append(a.value)
                elif isinstance(a, ast.JoinedStr):  # f-string
                    out.append("".join(v.value for v in a.values
                                       if isinstance(v, ast.Constant)))
    return out


def test_the_database_is_queried():
    src = ast.unparse(_heartbeat_fn())
    assert "pg_pool.acquire" in src, "heartbeat must actually hit the database"


def test_failure_branch_never_emits_the_signal():
    for handler in (n for n in ast.walk(_heartbeat_fn())
                    if isinstance(n, ast.ExceptHandler)):
        for text in _printed_strings(handler):
            assert SIGNAL not in text, (
                "failure branch prints %r, which CloudWatch counts as a live "
                "heartbeat" % text)


def test_success_path_still_emits_the_signal():
    assert any(SIGNAL in t for t in _printed_strings(_heartbeat_fn())), \
        "nothing prints %r any more — the alarm would fire constantly" % SIGNAL


def main():
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok ", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    print("\nAll heartbeat checks passed." if not failed else "\n%d failed." % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
