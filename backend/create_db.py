import asyncio
import asyncpg

import os
from urllib.parse import urlparse

async def main():
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/jobclaw")
    # Clean URL scheme for asyncpg
    clean_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(clean_url)
    user = parsed.username or os.getenv("PGUSER", "postgres")
    password = parsed.password or os.getenv("PGPASSWORD", "postgres")
    host = parsed.hostname or os.getenv("PGHOST", "localhost")
    port = parsed.port or int(os.getenv("PGPORT", "5432"))

    conn = await asyncpg.connect(user=user, password=password, host=host, port=port, database="postgres")
    try:
        await conn.execute("CREATE DATABASE jobclaw")
        print("Database 'jobclaw' created successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(main())
