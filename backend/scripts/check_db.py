import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
from app.core.config import settings
from app.database.models import Source

async def check():
    engine = create_async_engine(settings.DATABASE_URL)
    async with sessionmaker(engine, class_=AsyncSession)() as s:
        print('Total:', (await s.execute(select(func.count(Source.id)))).scalar())
        print('WP:', (await s.execute(select(func.count(Source.id)).where(Source.ats_type=='WordPress'))).scalar())
        print('Workable:', (await s.execute(select(func.count(Source.id)).where(Source.ats_type=='Workable'))).scalar())
        print('Unique domains:', (await s.execute(select(func.count(func.distinct(Source.domain))))).scalar())

asyncio.run(check())
