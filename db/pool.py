import asyncpg
from aws.secrets import get_rds_credentials
from config import RDS_HOST, RDS_DBNAME, RDS_PORT

async def create_db_pool():
    username, password = get_rds_credentials()
    pool = await asyncpg.create_pool(
        user=username,
        password=password,
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