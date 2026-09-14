# Job-Claw

An intelligent, full-stack job discovery, matching, and application orchestrator designed to find the best job opportunities from ATS sources and company career pages, score them against user profiles using LLMs, and seamlessly orchestrate applications.

## Architecture

Job-Claw is a monorepo consisting of two primary components:

### 1. [Backend](backend/README.md) (`/backend`)
A high-performance asynchronous Python control plane built on **FastAPI** and **PostgreSQL (asyncpg)**. 
- Orchestrates distributed background workers (via **ARQ** and **Redis**) to discover jobs from Greenhouse, Lever, Workday, and custom ATS systems.
- Employs a dual-sequence fallback LLM layer (Groq + Gemini) for canonicalization and candidate matching.
- Exposes REST APIs and SSE streams for real-time frontend integration.

### 2. [Frontend](frontend/README.md) (`/frontend`)
A modern, responsive dashboard built on **Next.js 15 (App Router)** and **TypeScript**.
- Designed with **Tailwind CSS**, **Shadcn UI**, and **Framer Motion** for a premium, highly responsive user experience.
- Provides real-time views into job discovery pipelines, LLM matching health, and candidate applications via SSE.

## Quick Start (Development)

To spin up the entire application locally, you will need Node.js, Python 3.10+, PostgreSQL, and Redis.

### Database & Redis Setup
Ensure you have PostgreSQL running on port 5432 and Redis running on port 6379.

### Starting the Backend
```bash
cd backend
python -m venv .venv
# Activate the virtual environment (.venv\Scripts\activate on Windows)
pip install -r requirements.txt

# Configure your environment
copy .env.example .env
# Edit .env to add your Postgres credentials and LLM API keys

# Setup the database
python create_db.py

# Start the FastAPI server
uvicorn app.main:app --reload --port 8000

# In a separate terminal, start the background ARQ worker
python -m arq app.workers.settings.WorkerSettings
```

### Starting the Frontend
```bash
cd frontend
npm install

# Start the Next.js dev server
npm run dev
# The UI will be available at http://localhost:3000
```

## Testing
Job-Claw uses `pytest` for backend unit tests and `Playwright` for frontend end-to-end testing.
See individual package readmes for test execution instructions.
