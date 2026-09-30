"""Self-check: the pool must pick up a rotated database password.

Run: python test_pool_credentials.py

The RDS-managed secret rotates every 7 days. asyncpg evaluates a callable `password`
on every new connection (connect_utils.py: `if callable(params.password)`), so passing
the fetch function rather than a fetched string is what makes rotation survivable.
Reading it once at startup cost nine days of scores in September 2026.
"""
import asyncio
import sys
import types

# Stub config + boto3 so this runs with no AWS and no .env.
sys.modules.setdefault("config", types.SimpleNamespace(
    RDS_SECRET_ARN="arn:test", AWS_REGION="eu-central-1",
    RDS_HOST="h", RDS_DBNAME="d", RDS_PORT=5432))

import db.pool as pool_mod

ROTATIONS = iter(["first-password", "rotated-password", "rotated-again"])
captured = {}


class _FakeConn:
    async def execute(self, *a, **k): return "SELECT 1"


class _FakeAcquire:
    async def __aenter__(self): return _FakeConn()
    async def __aexit__(self, *a): return False


class _FakePool:
    def acquire(self): return _FakeAcquire()


async def _fake_create_pool(**kwargs):
    captured.update(kwargs)
    return _FakePool()


def test_password_is_a_callable_not_a_string():
    assert callable(captured["password"]), \
        "password must be a callable so asyncpg re-reads it per connection"


def test_each_connection_sees_the_rotated_secret():
    # asyncpg calls this once per new connection; each call must hit the secret again.
    assert captured["password"]() == "rotated-password"
    assert captured["password"]() == "rotated-again"


def main():
    pool_mod.asyncpg = types.SimpleNamespace(create_pool=_fake_create_pool)
    pool_mod.get_rds_credentials = lambda: ("wordleadmin", next(ROTATIONS))
    asyncio.run(pool_mod.create_db_pool())

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok ", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    print("\nAll credential checks passed." if not failed else "\n%d failed." % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
