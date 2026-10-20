# Job-Claw Frontend

The Next.js 16 (App Router with Turbopack) dashboard UI for Job-Claw. Engineered for real-time job discovery, sub-millisecond filtering, interactive recommendations, and autonomous application tracking.

---

## 🛠️ Tech Stack

| Component | Technology | Version | Purpose |
|---|---|---|---|
| **Framework** | Next.js (App Router, Turbopack) | 16.3.4 | Server and client rendered application shell |
| **UI Library** | React | 19.0.0 | Component rendering and interactive state |
| **Language** | TypeScript | 5.0+ | Strict type safety and API contract definitions |
| **Styling** | Tailwind CSS v4 | 4.0+ | Custom dark-mode design system with glassmorphism |
| **Icons & Animation** | Lucide Icons, tw-animate-css | Latest | Modern iconography and responsive transitions |
| **Components** | Radix / Base UI / Shadcn UI | Accessible primitives | Accessible dialogs, dropdowns, tooltips, and badges |
| **HTTP Client** | Fetch API + AbortController | `lib/api.ts` | 30s resilient timeout, error handling, and query serialization |

---

## 🧭 Application Routes & Pages

| Route | Title | Key Features |
|---|---|---|
| **`/`** | **Discover Feed** | Real-time job search across fetched company listings. Sort by **Recently Posted** (`posted_at`), **Recently Discovered** (`discovered`), or **Highest Match Score** (`score`). Strict dropdown filters for **Degree** (MCA, B.Tech, M.Tech, BCA, Any Graduate) and **Experience** (Fresher, Junior 1–3 Yrs, Mid 3–5 Yrs, Senior 5+ Yrs). Verified direct apply links to authentic ATS career portals. |
| **`/recommendations`** | **Interactive Recommendations** | Candidate-Centric AI recommendations. Includes interactive filter bar (`q`, `role`, `degree`, `experience_level`, `location`, `scope`), match breakdown scores (0–100%), skill badges, missing skills, and fit reasons. |
| **`/sources`** | **Source Registry** | Management view for **19,153+ verified company boards**. Filter by ATS platform (BambooHR, Ashby, Zoho Recruit, Workday, etc.), crawl status, manual discovery trigger, and sync status. |
| **`/engines`** | **Discovery Engines** | Real-time monitoring of all 16 ATS discovery adapters and generic crawlers. Displays adapter status, execution counts, success rates, and engine metrics. |
| **`/saved-searches`** | **Saved Searches & Alerts** | User-saved query alerts, scheduled execution intervals, and new match notifications. |
| **`/agent`** | **Auto-Apply Agent** | Control center for autonomous Playwright application submission orchestration and profile synchronization. |
| **`/applications/[id]`**| **Application Details** | Detail review of drafted and submitted job applications with field-level inspection. |

---

## 🧩 Key Components

### 1. Job Card (`components/jobs/job-card.tsx`)
- **Direct ATS Badge**: Shows source platform (e.g., `Ashby`, `Greenhouse`, `Zoho Recruit`, `Workday`).
- **Authentic Job Posting Time Badge**: Differentiates authentic employer job post dates (`Posted 10h ago`, `Posted 1d ago` highlighted in cyber-lime `#c8f542`) from crawler discovery timestamps (`Found 5m ago`), powered by verified `jobs.posted_at` timestamps.
- **Ground-Truth Experience**: Distinct, color-coded badges:
  - `Fresher` (0–1 Yrs)
  - `Junior (1–3 Yrs)` (includes 2–3 yrs postings)
  - `Mid (3–5 Yrs)`
  - `Senior (5+ Yrs)`
- **Degree Requirement**: Strict degree tags (`MCA`, `B.Tech`, `M.Tech`, `BCA`).
- **Location & Corridor**: Highlights tech corridors (e.g., `Bangalore • Outer Ring Road`, `Chennai • OMR`, `Hyderabad • Hitec City`).
- **Verified Direct Apply Button**: Direct canonical application link opening the employer's official ATS portal in a new tab.

### 2. API Client (`lib/api.ts`)
- **30-Second Timeout**: Extended request timeout with `AbortSignal.timeout(30000)` to ensure large analytical and recommendation queries execute reliably without abort errors.
- **Graceful Error Recovery**: Custom `ApiError` class distinguishing between HTTP 408 / 504 timeouts, network disconnection, and server errors.
- **URL Parameter Serialization**: Automated handling of arrays, filters, and null-stripping for FastAPI endpoints.

---

## 🚀 Quick Start

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Configure environment (optional, defaults to http://127.0.0.1:8000)
# Create .env.local if targeting an alternative backend port
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > .env.local

# 3. Run development server (Turbopack enabled)
npm run dev
```

The application will be live at **http://localhost:3000**.

---

## 🧪 End-to-End Testing

```bash
# Run Playwright tests across browser engines
npx playwright test
```

