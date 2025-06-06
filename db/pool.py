import asyncpg
from aws.secrets import get_db_secret

async def create_db_pool():
    secret = get_db_secret()
    pool = await asyncpg.create_pool(
        user=secret['username'],
        password=secret['password'],
        database='postgres',
        host=secret['wordle-db.cjywummmsd5i.eu-central-1.rds.amazonaws.com'],
        port=5432,
        ssl='require',
        min_size=1,
        max_size=5,
        timeout=10
    )
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return pool