import asyncio
import os
import json
import re
import urllib.parse
import sys

# Add backend directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete, text
from app.database.models import Source
import uuid

DB_URL = "postgresql+asyncpg://postgres:Postpass123@localhost:5432/jobclaw"

engine = create_async_engine(DB_URL)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

def extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc if parsed.netloc else url.strip('/')
    except:
        return url

async def run_seed():
    async with AsyncSessionLocal() as db:
        # Do not truncate to preserve jobs!
        # await db.execute(text("TRUNCATE TABLE sources CASCADE;"))
        # await db.commit()
        
        # We'll use a dictionary to keep track of new sources, but we need to use ON CONFLICT DO NOTHING.
        # But SQLAlchemy add_all will throw an integrity error if domain exists.
        # Let's fetch existing domains to avoid inserting duplicates.
        existing = await db.execute(text("SELECT domain FROM sources"))
        existing_domains = {row[0] for row in existing}
        
        sources = {}

        # 1. Parse do.md
        do_md_path = r"d:\in test tools\job-claw\scaper\do.md"
        if os.path.exists(do_md_path):
            with open(do_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # find lines like: | Company Name | https://... |
                for line in content.split('\n'):
                    if line.startswith('|') and 'Company Name' not in line and '---' not in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 3:
                            company = parts[1]
                            url = parts[2]
                            if url.startswith('http'):
                                domain = extract_domain(url)
                                if domain not in existing_domains:
                                    sources[domain] = Source(
                                        id=str(uuid.uuid4()),
                                        domain=domain,
                                        start_url=url,
                                        is_active=True
                                    )

        # 2. Parse WordPress json
        wp_path = r"d:\in test tools\job-claw\scaper\apps\backend\data\targets\wordpress_target_sites.seed.json"
        if os.path.exists(wp_path):
            with open(wp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    url = item.get("homepage_url")
                    if url:
                        domain = extract_domain(url)
                        if domain not in existing_domains:
                            sources[domain] = Source(
                                id=str(uuid.uuid4()),
                                domain=domain,
                                start_url=url,
                                ats_type="WordPress",
                                is_active=True
                            )

        # 3. Parse Workable json
        wa_path = r"d:\in test tools\job-claw\scaper\apps\ever-jobs\scripts\seeds\workable-candidates.json"
        if os.path.exists(wa_path):
            with open(wa_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    slug = item.get("companySlug")
                    if slug:
                        domain = f"{slug}.workable.com"
                        if domain not in existing_domains:
                            start_url = f"https://apply.workable.com/{slug}/"
                            sources[domain] = Source(
                                id=str(uuid.uuid4()),
                                domain=domain,
                                start_url=start_url,
                                ats_type="workable",
                                is_active=True
                            )

        # Insert all
        db.add_all(sources.values())
        await db.commit()
        print(f"Successfully seeded {len(sources)} sources.")

if __name__ == "__main__":
    asyncio.run(run_seed())
