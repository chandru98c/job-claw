import asyncio
import asyncpg
import os

async def main():
    conn = await asyncpg.connect(user="postgres", password="Postpass123", host="localhost", port=5432, database="jobclaw")
    try:
        await conn.execute("DROP SCHEMA public CASCADE;")
        await conn.execute("CREATE SCHEMA public;")
        print("Database schema 'public' reset successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(main())
