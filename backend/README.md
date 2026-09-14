# Job-Claw Backend

The FastAPI control plane and Python scraping workers for Job-Claw.

## Tech Stack
| Component       | Technology                          |
|-----------------|-------------------------------------|
| API Framework   | FastAPI 0.115                       |
| Database        | PostgreSQL (via SQLAlchemy + asyncpg)|
| Migrations      | Alembic                            |
| Scraping        | Playwright, BeautifulSoup, httpx    |
| AI Providers    | Groq, Gemini (Dual Sequence Fallback)|
| Workers         | ARQ + Redis                      |
| ML              | scikit-learn (TF-IDF)               |

## Directory Structure
```
backend/
├── app/
│   ├── api/           # FastAPI route handlers
│   ├── core/          # LLM sequencer, Playwright orchestration, config
│   ├── database/      # SQLAlchemy models, session, migrations
│   ├── schemas/       # Pydantic request/response models
│   ├── workers/       # ARQ worker jobs (discovery, ATS, matching)
│   └── main.py        # FastAPI app entry point
├── docs/              # Backend-specific documentation
├── tests/             # pytest test suite
├── .env.example       # Environment variable template
└── requirements.txt   # Python dependencies
```

## Quick Start
```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env and configure
copy .env.example .env
# Edit .env with your DATABASE_URL and API keys

# 4. Run the server
uvicorn app.main:app --reload --port 8000
```
