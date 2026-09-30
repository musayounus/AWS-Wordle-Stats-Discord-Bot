import asyncpg
from aws.secrets import get_rds_credentials
from config import RDS_HOST, RDS_DBNAME, RDS_PORT


def _current_password():
    """Re-read the secret. asyncpg calls this for every new connection it opens.

    The RDS-managed secret rotates every 7 days. Reading the password once at startup
    meant that after the first rotation no new connection could authenticate: the bot
    stayed up, kept logging its heartbeat and answered Discord, but every database call
    failed. That went unnoticed for nine days in September 2026.
    """
    return get_rds_credentials()[1]


async def create_db_pool():
    """Create and return an asyncpg connection pool to RDS."""
    username, _ = get_rds_credentials()
    pool = await asyncpg.create_pool(
        user=username,
        password=_current_password,
        database=RDS_DBNAME,
        host=RDS_HOST,
        port=RDS_PORT,
        ssl="require",
        min_size=1,
        max_size=5,
        timeout=10
    )
    # verify connectivity
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return pool
