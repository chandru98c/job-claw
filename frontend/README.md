# Job-Claw Frontend

The Next.js 15 (App Router) dashboard UI for Job-Claw.

## Tech Stack
| Component       | Technology                          |
|-----------------|-------------------------------------|
| Framework       | Next.js 15 (App Router)             |
| Language        | TypeScript                          |
| Styling         | Tailwind CSS                        |
| UI Components   | Shadcn UI                           |
| Animations      | Framer Motion                       |
| State           | React Context / Zustand             |
| Testing         | Playwright                          |

## Pages
| Route              | Description                                         |
|--------------------|-----------------------------------------------------|
| `/`                | Dashboard - live metrics (jobs today, targets, health)|
| `/targets`         | Target ingestion & management                       |
| `/jobs`            | Normalized job browser with DataTable               |
| `/settings`        | Config, LLM Sequence drag-and-drop                  |
| `/task-center`     | Real-time execution log streaming (SSE)             |
| `/applications/[id]`| Dynamic application review and submission view     |

## Communication with Backend
- REST calls to `http://localhost:8000` for CRUD operations.
- SSE stream from `http://localhost:8000/api/tasks/stream` for real-time live execution logs.

## Quick Start
```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Run the development server
npm run dev
# Opens on http://localhost:3000
```

## E2E Testing
The frontend comes with a Playwright end-to-end test suite for validating the core application and submission flows against the backend API.

```bash
# 1. Start the backend API locally (required)
cd ../backend
uvicorn app.main:app --port 8000

# 2. Run Playwright tests
cd ../frontend
npx playwright test
```
