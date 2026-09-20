import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        # Delete from child tables where parent is NOT airbnb
        
        await session.execute(text("""
            DELETE FROM job_recommendations
            WHERE job_id IN (
                SELECT id FROM jobs 
                WHERE company_name NOT ILIKE '%airbnb%'
            )
        """))

        await session.execute(text("""
            DELETE FROM discovery_method_performances 
            WHERE source_id IN (
                SELECT id FROM sources 
                WHERE domain NOT ILIKE '%airbnb%'
            )
        """))
        
        await session.execute(text("""
            DELETE FROM job_source_provenances
            WHERE source_id IN (
                SELECT id FROM sources 
                WHERE domain NOT ILIKE '%airbnb%'
            ) OR job_id IN (
                SELECT id FROM jobs 
                WHERE company_name NOT ILIKE '%airbnb%'
            )
        """))
        
        await session.execute(text("""
            DELETE FROM job_versions
            WHERE job_id IN (
                SELECT id FROM jobs 
                WHERE company_name NOT ILIKE '%airbnb%'
            )
        """))
        
        # Delete dummy sources
        await session.execute(text("""
            DELETE FROM sources 
            WHERE domain NOT ILIKE '%airbnb%'
        """))
        
        # Delete dummy jobs
        await session.execute(text("""
            DELETE FROM jobs 
            WHERE company_name NOT ILIKE '%airbnb%'
        """))
        
        await session.commit()
        print('Cleanup complete.')

if __name__ == '__main__':
    asyncio.run(main())
