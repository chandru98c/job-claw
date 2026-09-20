"""
Discovery Engine: orchestrates the full deterministic discovery pipeline.

Flow:
  1. Input URL (and SourceConfig)
  2. Find all applicable strategies
  3. Load historical performance from DB
  4. Score and rank methods
  5. Sequential Top-5 Execution (Primary -> Sufficient? -> Fallback)
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import AsyncSessionLocal
from app.database.models import DiscoveryMethodPerformance

from app.discovery.registry import StrategyRegistry
from app.discovery.pipeline import CandidatePipeline
from app.discovery.budget import ResourceBudget, ResourceAccounting
from app.core.http import SafeHTTPClient, DomainPolicy
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryError,
    DiscoveryErrorType,
    CandidateState,
    SourceConfig,
)

logger = logging.getLogger(__name__)

@dataclass
class DiscoveryResult:
    """Complete result of a discovery engine run."""
    input_url: str
    raw_jobs: list[RawJob] = field(default_factory=list)
    results: list[StrategyExecutionResult] = field(default_factory=list)
    errors: list[DiscoveryError] = field(default_factory=list)
    accounting: dict = field(default_factory=dict)
    success: bool = True
    primary_method: Optional[str] = None
    fallback_methods_used: list[str] = field(default_factory=list)

class DiscoveryEngine:
    """
    Orchestrates deterministic job discovery using an Adaptive Method Router.
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        domain_policy: Optional[DomainPolicy] = None,
        budget: Optional[ResourceBudget] = None,
        event_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    ):
        self._registry = registry
        self._domain_policy = domain_policy or DomainPolicy()
        self._budget = budget or ResourceBudget()
        self._pipeline = CandidatePipeline(
            registry=registry,
            domain_policy=self._domain_policy,
        )
        self._event_callback = event_callback

    async def _emit(self, event_type: str, payload: dict):
        if self._event_callback:
            try:
                await self._event_callback(event_type, payload)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

    async def discover(self, input_url: str, source_config: Optional[SourceConfig] = None) -> DiscoveryResult:
        result = DiscoveryResult(input_url=input_url)
        accounting = ResourceAccounting(self._budget)
        await self._emit("discovery_started", {"url": input_url, "source_id": source_config.source_id if source_config else None})

        # 1. Identify all applicable strategies
        candidates = self._registry.find_candidates(input_url, source_config)
        accounting.record_candidate()
        await self._emit("candidates_generated", {"count": len(candidates)})

        if not candidates:
            result.errors.append(DiscoveryError(error_type=DiscoveryErrorType.UNSUPPORTED_SOURCE, message="No strategies recognized the input URL"))
            result.success = False
            return result

        # 2. Validate Candidates
        validated_candidates, _ = self._pipeline.validate_candidates(candidates)
        
        # Group by strategy_id
        methods_candidates = {}
        for c in validated_candidates:
            methods_candidates.setdefault(c.strategy_id, []).append(c)
            
        applicable_methods = list(methods_candidates.keys())

        # 3. Load Historical Performance
        performances = {}
        if source_config:
            async with AsyncSessionLocal() as session:
                stmt = select(DiscoveryMethodPerformance).where(
                    DiscoveryMethodPerformance.source_id == source_config.source_id,
                    DiscoveryMethodPerformance.method.in_(applicable_methods)
                )
                res = await session.execute(stmt)
                for perf in res.scalars():
                    performances[perf.method] = perf

        # 4. Score and Rank Methods
        ranked_methods = self._rank_methods(applicable_methods, methods_candidates, performances)
        top_5_methods = [m[0] for m in ranked_methods[:5]]
        
        await self._emit("methods_ranked", {"ranking": top_5_methods})

        if top_5_methods:
            result.primary_method = top_5_methods[0]
            
        # 5. Top-5 Sequential Fallback Execution
        for i, method_id in enumerate(top_5_methods):
            if not accounting.can_request() or accounting.is_expired():
                break

            if i > 0:
                result.fallback_methods_used.append(method_id)
                await self._emit("fallback_triggered", {"method": method_id})
                
            method_result = await self._execute_method(method_id, methods_candidates[method_id], accounting, result)
            
            # 6. Check Sufficiency
            perf = performances.get(method_id)
            if self._is_sufficient(method_result, perf):
                await self._emit("method_sufficient", {"method": method_id, "jobs": len(method_result.raw_jobs)})
                break
            else:
                await self._emit("method_insufficient", {"method": method_id, "jobs": len(method_result.raw_jobs)})

        # 7. Update Performance
        if source_config:
            await self._update_performances(source_config.source_id, result.results)

        result.accounting = accounting.summary()
        result.success = len(result.errors) == 0 or len(result.raw_jobs) > 0
        await self._emit("discovery_completed", {"success": result.success, "jobs_discovered": len(result.raw_jobs)})
        return result

    def _rank_methods(self, methods: list[str], candidates: dict, performances: dict) -> list[tuple[str, float]]:
        scores = []
        for method_id in methods:
            perf = performances.get(method_id)
            cands = candidates.get(method_id, [])
            priority = cands[0].priority if cands else 100
            
            if perf and perf.runs > 0:
                # Deterministic historical score
                yield_rate = perf.unique_jobs / max(perf.successful_runs, 1)
                validity = perf.valid_jobs / max(perf.jobs_found, 1)
                duplicate_rate = perf.duplicate_jobs / max(perf.jobs_found, 1)
                completeness = perf.avg_field_completeness if (perf.avg_field_completeness and perf.avg_field_completeness > 0) else 0.5
                latency_penalty = perf.avg_latency_ms * 0.001
                failure_penalty = perf.failure_rate * 50
                
                score = (yield_rate * validity * completeness * 10) - (duplicate_rate * 10) - latency_penalty - failure_penalty
            else:
                # Bootstrap score based on priority
                score = 1000.0 - priority
                
            scores.append((method_id, score))
            
        # Sort descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    async def _execute_method(self, method_id: str, candidates: list[StrategyCandidate], accounting: ResourceAccounting, result: DiscoveryResult) -> StrategyExecutionResult:
        combined_jobs = []
        combined_errors = []
        
        # Sort candidates for this method by priority
        for c in sorted(candidates, key=lambda c: c.priority):
            if not accounting.can_request() or accounting.is_expired():
                break
                
            exec_result = await self._pipeline.execute_candidate(c)
            result.results.append(exec_result)
            accounting.record_request(success=exec_result.success)
            
            if exec_result.raw_jobs:
                # Stamp the discovery_method
                for rj in exec_result.raw_jobs:
                    rj.provenance.discovery_method = method_id
                combined_jobs.extend(exec_result.raw_jobs)
                result.raw_jobs.extend(exec_result.raw_jobs)
                accounting.record_jobs(len(exec_result.raw_jobs))
                
            combined_errors.extend(exec_result.errors)
            result.errors.extend(exec_result.errors)
            
            # If the strategy generated sub-candidates (like sitemaps), we would handle them here.
            # But wait! If robots.txt yields sitemap_urls, the engine needs to process them!
            # The prompt requires us to reuse the existing strategy architecture.
            discovered_sitemaps = getattr(exec_result, '_discovered_sitemaps', [])
            discovered_job_urls = getattr(exec_result, '_discovered_job_urls', [])
            
            if discovered_sitemaps:
                await self._process_discovered_sitemaps(discovered_sitemaps, result, accounting, discovered_job_urls, method_id)
                
            if discovered_job_urls:
                extracted = await self._try_ats_on_discovered_urls(discovered_job_urls, result, accounting, method_id)
                combined_jobs.extend(extracted)
                
        # Return a synthetic result representing the method run
        return StrategyExecutionResult(
            strategy_id=method_id,
            candidate_id="aggregated",
            success=len(combined_errors) == 0,
            raw_jobs=combined_jobs,
            errors=combined_errors,
        )

    def _is_sufficient(self, result: StrategyExecutionResult, perf: Optional[DiscoveryMethodPerformance]) -> bool:
        if not result.success:
            return False
            
        jobs_found = len(result.raw_jobs)
        
        if perf and perf.runs > 0:
            historical_baseline = perf.jobs_found / max(perf.successful_runs, 1)
            # Threshold: must yield at least 50% of the historical average, OR > 0 if baseline is very small
            if historical_baseline < 2:
                return jobs_found > 0
            return jobs_found >= (historical_baseline * 0.5)
        else:
            return jobs_found > 0

    async def _process_discovered_sitemaps(self, sitemap_urls, result, accounting, discovered_job_urls, parent_method):
        sitemap_strategy = self._registry.get("sitemap_discovery")
        if not sitemap_strategy: return
        for sm_url in sitemap_urls:
            if not accounting.can_request(): break
            c = StrategyCandidate(strategy_id="sitemap_discovery", target_url=sm_url, evidence="Discovered via robots.txt", confidence=0.7, source="robots_txt", priority=60)
            c = self._pipeline.validate_candidate(c)
            if c.state != CandidateState.VALIDATED: continue
            accounting.record_candidate()
            exec_result = await self._pipeline.execute_candidate(c)
            result.results.append(exec_result)
            accounting.record_request(success=exec_result.success)
            discovered_job_urls.extend(getattr(exec_result, '_discovered_job_urls', []))

    async def _try_ats_on_discovered_urls(self, job_urls, result, accounting, parent_method):
        extracted_jobs = []
        for job_url in job_urls:
            if not accounting.can_request(): break
            ats_candidates = [c for c in self._registry.find_candidates(job_url) if c.strategy_id not in ("sitemap_discovery", "robots_txt_discovery", "career_page_discovery")]
            if not ats_candidates: continue
            
            for c in ats_candidates:
                if not accounting.can_request(): break
                c = self._pipeline.validate_candidate(c)
                if c.state != CandidateState.VALIDATED: continue
                accounting.record_candidate()
                exec_result = await self._pipeline.execute_candidate(c)
                result.results.append(exec_result)
                accounting.record_request(success=exec_result.success)
                if exec_result.raw_jobs:
                    for rj in exec_result.raw_jobs: rj.provenance.discovery_method = parent_method
                    extracted_jobs.extend(exec_result.raw_jobs)
                    result.raw_jobs.extend(exec_result.raw_jobs)
                    accounting.record_jobs(len(exec_result.raw_jobs))
                result.errors.extend(exec_result.errors)
        return extracted_jobs

    async def _update_performances(self, source_id: str, results: list[StrategyExecutionResult]):
        # Aggregate results by strategy_id
        aggs = {}
        for r in results:
            sid = r.strategy_id
            if sid not in aggs:
                aggs[sid] = {"success": False, "errors": 0, "jobs": [], "latency": 0.0, "count": 0}
            
            if r.success: aggs[sid]["success"] = True
            if r.errors: aggs[sid]["errors"] += len(r.errors)
            aggs[sid]["jobs"].extend(r.raw_jobs)
            aggs[sid]["latency"] += r.duration_seconds
            aggs[sid]["count"] += 1
            
        async with AsyncSessionLocal() as session:
            # Note: PostgreSQL UPSERT using ON CONFLICT DO UPDATE
            from sqlalchemy.dialects.postgresql import insert
            
            for sid, agg in aggs.items():
                now_utc = datetime.now(timezone.utc)
                
                unique_ids = set()
                unique_count = 0
                field_completeness_sum = 0.0
                
                for job in agg["jobs"]:
                    # Local uniqueness
                    s_id = job.provenance.source_job_id
                    if s_id:
                        if s_id not in unique_ids:
                            unique_ids.add(s_id)
                            unique_count += 1
                    else:
                        unique_count += 1
                        
                    # Field completeness
                    fields = ["title", "company", "location", "description", "apply_url"]
                    filled = sum(1 for f in fields if getattr(job, f, None))
                    field_completeness_sum += (filled / len(fields))
                    
                total_jobs = len(agg["jobs"])
                avg_field_completeness = (field_completeness_sum / total_jobs) if total_jobs > 0 else 0.0
                duplicate_jobs = total_jobs - unique_count
                
                stmt = insert(DiscoveryMethodPerformance).values(
                    id=f"{source_id}_{sid}",
                    source_id=source_id,
                    method=sid,
                    runs=1,
                    successful_runs=1 if agg["success"] else 0,
                    failed_runs=1 if not agg["success"] else 0,
                    jobs_found=total_jobs,
                    valid_jobs=total_jobs, # Without DB access, assume valid initially
                    unique_jobs=unique_count,
                    duplicate_jobs=duplicate_jobs,
                    invalid_jobs=0,
                    avg_latency_ms=(agg["latency"] / max(agg["count"], 1)) * 1000,
                    avg_field_completeness=avg_field_completeness,
                    failure_rate=1.0 if not agg["success"] else 0.0,
                    quality_score=0.0,
                    last_run_at=now_utc,
                    last_success_at=now_utc if agg["success"] else None,
                    last_failure_at=now_utc if not agg["success"] else None,
                ).on_conflict_do_update(
                    index_elements=['source_id', 'method'],
                    set_={
                        "runs": DiscoveryMethodPerformance.runs + 1,
                        "successful_runs": DiscoveryMethodPerformance.successful_runs + (1 if agg["success"] else 0),
                        "failed_runs": DiscoveryMethodPerformance.failed_runs + (1 if not agg["success"] else 0),
                        "jobs_found": DiscoveryMethodPerformance.jobs_found + total_jobs,
                        "valid_jobs": DiscoveryMethodPerformance.valid_jobs + total_jobs,
                        "unique_jobs": DiscoveryMethodPerformance.unique_jobs + unique_count,
                        "duplicate_jobs": DiscoveryMethodPerformance.duplicate_jobs + duplicate_jobs,
                        # avg latency is moving avg
                        "avg_latency_ms": (DiscoveryMethodPerformance.avg_latency_ms * DiscoveryMethodPerformance.runs + ((agg["latency"] / max(agg["count"], 1)) * 1000)) / (DiscoveryMethodPerformance.runs + 1),
                        "avg_field_completeness": (DiscoveryMethodPerformance.avg_field_completeness * DiscoveryMethodPerformance.runs + avg_field_completeness) / (DiscoveryMethodPerformance.runs + 1),
                        "failure_rate": (DiscoveryMethodPerformance.failed_runs + (1 if not agg["success"] else 0)) / (DiscoveryMethodPerformance.runs + 1),
                        "last_run_at": now_utc,
                        "last_success_at": now_utc if agg["success"] else DiscoveryMethodPerformance.last_success_at,
                        "last_failure_at": now_utc if not agg["success"] else DiscoveryMethodPerformance.last_failure_at,
                    }
                )
                await session.execute(stmt)
            await session.commit()
