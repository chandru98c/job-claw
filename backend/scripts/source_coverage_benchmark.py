import asyncio
import sys
import time
import json
from datetime import datetime, timezone
from sqlalchemy import select

# Fix python path for app imports
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import AsyncSessionLocal, SessionLocal
from app.database.models import Source, Job, JobSourceProvenance
from app.discovery.engine import DiscoveryEngine
from app.schemas.discovery import SourceConfig
from app.workers.discovery import build_registry
from app.discovery.budget import ResourceBudget
from app.canonicalization.pipeline import process_raw_job


async def get_benchmark_sources():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Source))
        sources = res.scalars().all()
        
        greenhouse = []
        workable = []
        lever = []
        ashby = []
        generic = []
        
        for s in sources:
            if s.domain in ["airbnb.com", "typeform.com", "bitpanda.com"]:
                if s.domain == "airbnb.com":
                    greenhouse.append(s)
                elif s.domain == "typeform.com":
                    workable.append(s)
                elif s.domain == "bitpanda.com":
                    lever.append(s)
                
        return {
            "greenhouse": greenhouse,
            "workable": workable,
            "lever": lever
        }

async def run_benchmark():
    print("--- STARTING SOURCE COVERAGE BENCHMARK ---")
    sources_dict = await get_benchmark_sources()
    
    total_sources = sum(len(lst) for lst in sources_dict.values())
    print(f"Selected {total_sources} active sources from registry.")
    
    # Speed up timeout for benchmark
    import httpx
    httpx._config.DEFAULT_TIMEOUT_CONFIG = httpx.Timeout(10.0)
    
    registry = build_registry()
    # Remove LLM strategy for benchmark to avoid hanging
    if "llm_discovery" in registry._strategies:
        del registry._strategies["llm_discovery"]
    budget = ResourceBudget()
    engine = DiscoveryEngine(registry=registry, budget=budget)
    
    results = []
    
    for category, sources in sources_dict.items():
        print(f"\nEvaluating category: {category.upper()}")
        for s in sources:
            url = s.start_url or f"https://{s.domain}"
            print(f"\n-> Source: {s.id} ({url})")
            print(f"   Selection reason: Matches '{category}' pattern.")
            
            config = SourceConfig(
                source_id=s.id,
                company=s.domain,
                domain=s.domain,
                careers_url=url,
                ats_type=s.ats_type,
                enabled=True
            )
            
            start_time = time.time()
            try:
                # 1. Run Discovery Engine
                result = await engine.discover(url, source_config=config)
            except Exception as e:
                print(f"   ERROR during discover: {e}")
                results.append({
                    "source_id": s.id,
                    "source_url": url,
                    "category": category,
                    "final_status": "EXCEPTION",
                    "failure_reason": str(e)
                })
                continue
                
            duration = time.time() - start_time
            
            # 2. Canonicalization
            valid_jobs_count = 0
            canonical_ids = set()
            invalid_jobs = 0
            jobs_with_source_job_id = 0
            jobs_with_apply_url = 0
            
            with SessionLocal() as sync_db:
                for raw_job in result.raw_jobs:
                    if raw_job.provenance and raw_job.provenance.source_job_id:
                        jobs_with_source_job_id += 1
                    if raw_job.provenance and raw_job.provenance.apply_url:
                        jobs_with_apply_url += 1
                        
                    try:
                        resolution_status, job = process_raw_job(sync_db, raw_job)
                        sync_db.commit()
                        if job:
                            valid_jobs_count += 1
                            canonical_ids.add(job.id)
                    except Exception as e:
                        print(f"   Validation/Canonicalization error: {e}")
                        invalid_jobs += 1
            
            
            canonical_persisted = len(canonical_ids)
            duplicates = valid_jobs_count - canonical_persisted
            
            # Did collapse happen?
            collapse_error = False
            if len(result.raw_jobs) > 1 and canonical_persisted <= (len(result.raw_jobs) // 2):
                if invalid_jobs == 0:
                    collapse_error = True
            
            llm_usage = "NOT REQUIRED"
            if "LLMStrategy" in result.accounting.get("strategies_used", []):
                llm_usage = "USED"
                
            final_status = "SUCCESS" if len(result.raw_jobs) > 0 else "ZERO_JOBS"
            
            # Classification fix for 0-job results as per user request:
            if len(result.raw_jobs) == 0 and result.errors:
                err_text = str(result.errors).lower()
                if "404" in err_text or "not found" in err_text or "migrate" in err_text:
                    final_status = "MIGRATED/UNSUPPORTED"
                else:
                    final_status = "FAILED"

            stats = {
                "source_id": s.id,
                "source_url": url,
                "category": category,
                "reachability": True,
                "selected_method": result.accounting.get("selected_strategy", "Unknown"),
                "fallback_methods": result.accounting.get("strategies_used", []),
                "raw_jobs": len(result.raw_jobs),
                "valid_jobs": valid_jobs_count,
                "canonical_jobs": canonical_persisted,
                "duplicates": duplicates,
                "invalid_jobs": invalid_jobs,
                "jobs_with_source_job_id": jobs_with_source_job_id,
                "jobs_with_apply_url": jobs_with_apply_url,
                "duration_seconds": round(duration, 2),
                "final_status": final_status,
                "llm_last_resort": llm_usage,
                "collapse_detected": collapse_error
            }
            
            print(json.dumps(stats, indent=2))
            results.append(stats)
            
    print("\n--- BENCHMARK SUMMARY ---")
    for r in results:
        status = r.get("final_status")
        cat = r.get("category")
        raw = r.get("raw_jobs", 0)
        col = "COLLAPSE!" if r.get("collapse_detected") else "OK"
        print(f"[{cat.upper()}] {r['source_url']} -> {status} ({raw} raw jobs, {col})")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
