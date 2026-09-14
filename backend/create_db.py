import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(user="postgres", password="Postpass123", host="localhost", port=5432, database="postgres")
    try:
        await conn.execute("CREATE DATABASE jobclaw")
        print("Database 'jobclaw' created successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(main())
