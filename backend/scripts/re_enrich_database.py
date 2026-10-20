import sys
import os
import asyncio
import time
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.database import AsyncSessionLocal, engine
from app.canonicalization.enrich import extract_degree, extract_experience
from app.canonicalization.normalize import clean_location_display

INDIA_KEYWORDS = (
    "india", "chennai", "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad",
    "pune", "noida", "gurgaon", "gurugram", "kolkata", "ahmedabad", "coimbatore",
    "tamil nadu", "karnataka", "telangana", "maharashtra"
)

async def run_re_enrichment(batch_size: int = 1000, max_records: int = None):
    print("=" * 80)
    print("JOB CLAW CANONICAL RE-ENRICHMENT ENGINE")
    print("Fixing Degree False Positives, Experience Normalization & Location Accuracy")
    print("=" * 80)
    
    start_time = time.time()
    total_processed = 0
    total_edu_updated = 0
    total_exp_updated = 0
    total_loc_updated = 0

    # Query count of jobs needing inspection
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("SELECT count(*) FROM jobs;"))
        total_jobs = res.scalar() or 0
        print(f"Total jobs in database: {total_jobs:,}")

    last_id = None
    limit = batch_size

    while True:
        if max_records and total_processed >= max_records:
            break

        async with AsyncSessionLocal() as session:
            if last_id is None:
                query = text("""
                    SELECT id, title, location, education_level, experience_level, LEFT(description, 6000), remote_status
                    FROM jobs
                    ORDER BY id ASC
                    LIMIT :limit;
                """)
                res = await session.execute(query, {"limit": limit})
            else:
                query = text("""
                    SELECT id, title, location, education_level, experience_level, LEFT(description, 6000), remote_status
                    FROM jobs
                    WHERE id > :last_id
                    ORDER BY id ASC
                    LIMIT :limit;
                """)
                res = await session.execute(query, {"last_id": last_id, "limit": limit})
            rows = res.fetchall()

            if not rows:
                break

            last_id = rows[-1][0]
            updates = []
            for r in rows:
                jid, title, loc, edu, exp, desc, remote = r
                
                # 1. Precise Degree
                new_edu = extract_degree(title) or extract_degree(desc)
                
                # 2. Candidate-anchored Experience
                new_exp = extract_experience(title, desc)
                
                # 3. Location Normalization
                new_loc = loc
                if loc == "India":
                    desc_lower = (desc or "").lower()
                    has_india = any(k in desc_lower for k in INDIA_KEYWORDS)
                    if not has_india:
                        new_loc = "Remote" if (remote == "remote" or "remote" in desc_lower) else "Unspecified"
                elif loc:
                    new_loc = clean_location_display(loc)

                # Check if change is needed
                changed = False
                if edu != new_edu:
                    changed = True
                    total_edu_updated += 1
                if exp != new_exp:
                    changed = True
                    total_exp_updated += 1
                if loc != new_loc:
                    changed = True
                    total_loc_updated += 1

                if changed:
                    updates.append({
                        "b_id": jid,
                        "b_edu": new_edu,
                        "b_exp": new_exp,
                        "b_loc": new_loc
                    })

            if updates:
                # Perform batch update
                await session.execute(
                    text("""
                        UPDATE jobs
                        SET education_level = :b_edu,
                            experience_level = :b_exp,
                            location = :b_loc,
                            updated_at = NOW()
                        WHERE id = :b_id;
                    """),
                    updates
                )
                await session.commit()

            total_processed += len(rows)
            
            elapsed = time.time() - start_time
            rate = total_processed / elapsed if elapsed > 0 else 0
            print(f"Processed: {total_processed:,}/{total_jobs:,} | Edu Fixed: {total_edu_updated:,} | Exp Fixed: {total_exp_updated:,} | Loc Fixed: {total_loc_updated:,} ({rate:.0f} jobs/s)", flush=True)

    await engine.dispose()
    print("=" * 80)
    print("RE-ENRICHMENT COMPLETE")
    print(f"Total Processed: {total_processed:,}")
    print(f"Degree Field Fixed: {total_edu_updated:,}")
    print(f"Experience Field Fixed: {total_exp_updated:,}")
    print(f"Location Field Fixed: {total_loc_updated:,}")
    print(f"Elapsed Time: {time.time() - start_time:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_re_enrichment())
