import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        res = await conn.execute(text('SELECT COUNT(*) FROM jobs'))
        print('Jobs count:', res.scalar())
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
