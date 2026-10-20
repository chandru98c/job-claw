# Job-Claw Backend

The FastAPI asynchronous control plane, multi-ATS discovery engine, canonicalization pipeline, and distributed background workers for Job-Claw.

---

## 🛠️ Tech Stack & Dependencies

| Component | Technology | Version | Purpose |
|---|---|---|---|
| **API Framework** | FastAPI | 0.115+ | Asynchronous REST endpoints, search, recommendations & SSE |
| **ASGI Server** | Uvicorn | 0.32+ | High-throughput asynchronous server |
| **Database ORM** | SQLAlchemy + asyncpg | 2.0+ / 0.30+ | Fully asynchronous PostgreSQL connection pool |
| **Migrations** | Alembic | 1.13+ | Schema migrations (including `education_level`, indices) |
| **Worker Queue** | ARQ + Redis | 0.26+ / 5.2+ | Async task distribution for discovery, freshness, and alerts |
| **HTTP Client** | HTTPX | 0.27+ | Async HTTP client with strict timeout, retry, and SSRF guard |
| **HTML / XML** | BeautifulSoup4, defusedxml | 4.12+ / 0.7+ | Safe HTML/XML parsing with XXE protection |
| **AI Matching** | Groq & Google Gemini | SDKs | Dual-sequence candidate profile scoring with fallback |
| **Full-Text & ML** | pg_trgm, scikit-learn | 1.5+ | PostgreSQL trigram fuzzy search and TF-IDF similarity |

---

## 📂 Directory Structure

```
backend/
├── app/
│   ├── api/                   # FastAPI route endpoints
│   │   ├── engines.py         # Engine discovery triggers, stats, and controls
│   │   ├── jobs.py            # Job search, details, direct apply links, filters
│   │   ├── recommendations.py # Interactive candidate recommendation scoring
│   │   ├── sources.py         # Source registry CRUD, bulk sync, crawl triggers
│   │   ├── system.py          # Health check, system status, Redis/DB metrics
│   │   ├── tasks.py           # ARQ background task status & SSE streaming
│   │   └── profiles.py        # Candidate profiles & skill management
│   ├── canonicalization/      # RawJob ingestion, deduplication & enrichment
│   │   ├── pipeline.py        # Date ingestion, provenance, version history
│   │   ├── enrich.py          # Strict degree, experience & corridor extraction
│   │   └── normalize.py       # Title, company, location & URL cleaning
│   ├── core/                  # Security & foundational utilities
│   │   ├── config.py          # Pydantic v2 application settings (.env)
│   │   ├── http.py            # SafeHTTPClient with domain rate limiting & SSRF guard
│   │   └── llm.py             # Dual-sequence Groq (Llama 3.3) -> Gemini fallback
│   ├── database/              # PostgreSQL schema, connection & models
│   │   ├── database.py        # Async engine & sessionmaker (AsyncSessionLocal)
│   │   └── models.py          # SQLAlchemy models: Job, Source, Task, Profile, etc.
│   ├── discovery/             # Discovery engine & ATS adapters
│   │   ├── adapters/          # 16 direct ATS and aggregator adapters
│   │   ├── strategies/        # robots.txt, sitemap, career page, and LLM strategies
│   │   ├── engine.py          # Discovery orchestration & adaptive ranking
│   │   └── interfaces.py      # Base ATSAdapter & DiscoveryStrategy protocols
│   ├── schemas/               # Pydantic validation schemas
│   │   ├── search.py          # Search query & response schemas (JobResponse)
│   │   ├── recommendation.py  # Recommendation filter & match result schemas
│   │   └── discovery.py       # RawJob, StrategyCandidate, ExecutionResult
│   ├── services/              # Core business services
│   │   ├── search.py          # SearchService with multi-token SQL condition builder
│   │   └── recommendation_engine.py # Interactive profile match scoring engine
│   └── workers/               # ARQ background task workers
│       ├── discovery.py       # Source crawl and extraction worker
│       └── settings.py        # WorkerSettings, cron jobs, Redis connection
├── config/
│   └── registry.yaml          # Git-authoritative registry: 19,153+ verified sources
├── scripts/                   # Migration & administrative CLI utilities
│   ├── sync_registry.py       # Sync registry.yaml -> PostgreSQL sources table
│   ├── seed_registry.py       # Initialize default sources
│   ├── validate_registry.py   # Registry YAML validator
│   ├── re_enrich_database.py  # Batch re-enrichment utility across canonical jobs
│   └── inspect_locations.py   # Diagnostic utility for location normalization
├── alembic/                   # Database migrations
├── tests/                     # Unit, integration, and adapter test suite
└── requirements.txt           # Python package dependencies
```

---

## 🔌 Discovery System & ATS Adapters

Job-Claw implements direct public API/JSON extraction for 16 major applicant tracking systems and platform types in `app/discovery/adapters/`:

| Adapter | Module | Sources Count | Native Date Extraction (`posted_at`) |
|---|---|---|---|
| **BambooHR** | `bamboohr.py` | 5,632 | `job.get("postedDate")` |
| **Ashby** | `ashby.py` | 3,457 | `publishedAt` / `createdAt` from `__NEXT_DATA__` |
| **Personio** | `personio.py` | 2,463 | `createdAt` ISO timestamp |
| **Teamtailor** | `teamtailor.py` | 1,464 | `created-at` from JSON API |
| **Breezy HR** | `breezy.py` | 1,383 | `creation_date` / `updated_date` |
| **Zoho Recruit** | `zohorecruit.py` | 1,248 | `Date_Posted` / `Date_Created` |
| **Recruitee** | `recruitee.py` | 1,204 | `created_at` / `published_at` |
| **Greenhouse** | `greenhouse.py` | 811 | `updated_at` / `first_published` |
| **Workable** | `workable.py` | 400 | `published_on` / `created_at` |
| **SmartRecruiters** | `smartrecruiters.py` | 219 | `releasedDate` |
| **Lever** | `lever.py` | 193 | `createdAt` epoch timestamp |
| **Keka** | `keka.py` | 184 | `postedOn` / `createdDate` |
| **Darwinbox** | `darwinbox.py` | 164 | `posted_date` |
| **Workday CXS** | `workday.py` | 23 | `postedOn` / `postedDate` |
| **WordPress Boards**| `wordpress.py` | 7 | RSS / JSON `date_gmt` |
| **Naukri Aggregator**| `naukri.py` | Aggregator | Indian tech market scraper |

---

## ⚡ Canonicalization & Database Indexing

### 1. Ingestion & Posting Date Normalization (`pipeline.py`)
- Each `RawJob` carries native `posted_at`.
- Canonicalization assigns `last_source_seen_at = raw_job.posted_at or raw_job.discovered_at`.
- When jobs are rediscovered, `last_source_seen_at` is updated only if newer, preserving initial posting integrity.

### 2. Strict Degree Isolation (`enrich.py`)
- Eliminates substring confusion between `MCA` and `B.Tech` using strict word boundaries:
  - **MCA**: `r"(?i)\b(mca|m\.c\.a|master of computer applications)\b"`
  - **B.Tech**: `r"(?i)\b(b\.?tech|bachelor of technology|b\.?e\.?|bachelor of engineering)\b"`
  - **M.Tech**: `r"(?i)\b(m\.?tech|master of technology|m\.?e\.?|master of engineering)\b"`
  - **BCA**: `r"(?i)\b(bca|b\.c\.a|bachelor of computer applications)\b"`
  - **Any Graduate**: Explicitly tagged without contaminating specific degree queries.

### 3. Ground-Truth Experience Categorization (`enrich.py`)
- Standardizes experience brackets into 4 mutually exclusive levels:
  - `fresher`: 0–1 Years
  - `junior`: 1–3 Years (correctly categorizes "2-3 years" and "1-3 years" requirements)
  - `mid`: 3–5 Years
  - `senior`: 5+ Years

### 4. Database Indexing Strategy (Sub-Millisecond Querying)
Across all fetched jobs, queries execute in **< 1 ms** due to specialized PostgreSQL indexes:
```sql
-- Primary sorting index (0.135 ms query latency)
CREATE INDEX ix_jobs_seen_desc ON jobs USING btree (last_source_seen_at DESC NULLS LAST);
CREATE INDEX ix_jobs_status_seen ON jobs USING btree (status, last_source_seen_at DESC NULLS LAST);

-- Trigram GIN indexes for fuzzy search
CREATE INDEX ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops);
CREATE INDEX ix_jobs_company_name_trgm ON jobs USING gin (company_name gin_trgm_ops);
CREATE INDEX ix_jobs_location_trgm ON jobs USING gin (location gin_trgm_ops);

-- B-Tree indexes for authentic posting date & structured facets
CREATE INDEX ix_jobs_posted_at_desc ON jobs USING btree (posted_at DESC NULLS LAST);
CREATE INDEX ix_jobs_status_posted ON jobs USING btree (status, posted_at DESC NULLS LAST);
CREATE INDEX ix_jobs_education_level ON jobs USING btree (education_level);
CREATE INDEX ix_jobs_experience_level ON jobs USING btree (experience_level);
CREATE INDEX ix_jobs_role_category ON jobs USING btree (role_category);
CREATE INDEX ix_jobs_salary ON jobs USING btree (salary_min, salary_max);
CREATE INDEX ix_jobs_remote_status ON jobs USING btree (remote_status);
```

---

## 🔍 Search & Recommendations Engine

### Multi-Token Context Search (`services/search.py`)
- Accepts free-form queries (`q=frontend react`, `q=developer chennai mca`).
- **Authentic Posting Date Sorting**:
  - `sort_by=posted_at` (default): Strictly sorts by authentic employer post timestamp (`Job.posted_at.desc().nullslast()`), ensuring jobs posted today and yesterday appear first.
  - `sort_by=discovered`: Sorts by crawler discovery time (`Job.last_source_seen_at.desc()`).
  - `sort_by=score`: Sorts by relevance match score.
- Evaluates multi-token queries across `title`, `company_name`, `role_category`, `location`, and `education_level` using trigrams and ILIKE boundaries without truncating words.

### Interactive Recommendations (`services/recommendation_engine.py`)
- Endpoint: `GET /recommendations`
- Accepts interactive filtering: `q`, `role`, `degree`, `experience_level`, `location`, `scope`.
- Scores candidate profile matches based on skill overlap, title match, location preference, and structured requirements with transparent scoring reasons.

---

## 🚀 Quick Start & Operations

### 1. Environment Setup
```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 2. Database Migrations & Sync
```bash
# Run migrations
alembic upgrade head

# Sync 19,153+ verified company sources from registry.yaml to PostgreSQL
python scripts/sync_registry.py

# Optional: Run full re-enrichment across canonical jobs
python scripts/re_enrich_database.py
```

### 3. Run FastAPI API Server
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive OpenAPI documentation is live at **http://localhost:8000/docs**.

### 4. Run ARQ Background Worker
```bash
python -m arq app.workers.settings.WorkerSettings
```

---

## 🧪 Testing

```bash
# Run complete backend test suite
pytest -v

# Run specific adapter tests
pytest tests/test_discovery.py -v
```

