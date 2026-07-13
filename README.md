# AI Job Hunter v9 🤖

An autonomous agent that monitors company career pages **and** job aggregators (Naukri, Instahyre, Cutshort, Wellfound, Indeed, Glassdoor) for **Data Science / AI-ML / Software Engineering** openings in Pune and India, deduplicates alerts, and notifies you via email.

---

## What's New in v3

- **Email-only notifications** — Telegram and WhatsApp dropped for simplicity
- **Job aggregator sources** — Naukri.com, Instahyre, Cutshort, Wellfound (AngelList) added alongside direct company scrapers
- **Broader role coverage** — now tracks SDE, Backend, Frontend, Full-stack, Mobile, DevOps roles in addition to DS/AI-ML
- **Expanded company list** — 28+ companies active from day one (Phase 1 + Phase 2 pulled forward)
- **6-hour run cycle** — runs every 6 hours to catch postings faster
- **Per-run summary** — detailed pipeline stats logged every run

## What's New in v4 & v5

- **Digest Emails (v4)**: You now get a single digest email per run with all the jobs, instead of one email per job. Skips sending if 0 jobs are found.
- **Experience Filter (v4/v5)**: A new keyword and semantic hybrid filter explicitly designed to target fresher/entry-level roles and reject senior/experienced roles.
- **Local Semantic Classifier (v5)**: Uses `sentence-transformers` locally to perform bulk classification for free, massively reducing Gemini API quota usage.
- **Quota Tracking (v5)**: Daily Gemini API calls are now logged to the local SQLite database to monitor usage limits.

## What's New in v9

- **8-hour GitHub Actions schedule** — runs automatically every 8 hours without your laptop on; commits `jobs.db` back to the repo so state persists.
- **Streamlit Dashboard** — browse all jobs, filter by company/source/date, one-click apply links, add new companies from the UI, and view analytics.
- **Indeed & Glassdoor scrapers** — two new aggregator sources for broader job coverage.
- **Startup Discovery script** — weekly/on-demand tool to find new Pune/India AI-ML startups, auto-detect their ATS, and add them to `companies.json`.
- **Expanded role keywords** — 30+ new role titles added across DS/AI-ML and SDE tracks, with matching updates to the semantic classifier and LLM prompt.

---

## Quick Start

### 1. Install dependencies

```bash
cd ai-job-hunter
pip install -r requirements.txt
playwright install chromium   # for JS-rendered career pages
```

> [!NOTE]
> **First Run**: The first time you run the agent, it will download the `all-MiniLM-L6-v2` model weights (~80MB) for the local semantic classifier. It needs internet access for this initial download, and will cache it locally for all future runs.

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your credentials:
#   SMTP_USER + SMTP_PASS + ALERT_EMAIL_TO  (Gmail App Password recommended)
#   GOOGLE_API_KEY                           (free at aistudio.google.com)
```

### 3. Run the pipeline

```bash
# Single run (production)
python -m scheduler.run --mode once

# Dry run — see what would be found without saving or notifying
python -m scheduler.run --mode dry-run

# Scheduled run (stays running, fires every RUN_INTERVAL_HOURS hours)
python -m scheduler.run --mode scheduled
```

---

## Architecture

```
scrapers/
  greenhouse.py     → Greenhouse API (generic)
  lever.py          → Lever API (generic, with pagination)
  ashby.py          → Ashby API (generic, with pagination)
  naukri.py         → Naukri.com aggregator (keyword + location search)
  instahyre.py      → Instahyre aggregator
  cutshort.py       → Cutshort aggregator
  wellfound.py      → Wellfound/AngelList aggregator
  indeed.py         → Indeed aggregator (v9)
  glassdoor.py      → Glassdoor aggregator (v9)
  custom/           → Per-company HTML scrapers

pipeline/
  normalizer.py     → Standardise to consistent schema (incl. source field)
  location_filter.py → Keep only Pune/India jobs
  role_filter.py    → Keyword whitelist (DS, AI-ML, SDE, Backend, etc.) — expanded in v9
  semantic_classifier.py → Local sentence-transformers relevance check
  experience_filter.py   → Fresher/entry-level experience filter
  llm_classifier.py → Gemini Flash yes/no relevance check
  dedup.py          → SHA-256 hash deduplication

dashboard/
  app.py            → Streamlit dashboard (v9)

scripts/
  discover_startups.py → Startup discovery tool (v9)

database/           → SQLite storage (jobs + run_log + api_quota tables)
notifier/           → Email only (v3)
scheduler/run.py    → Main orchestrator
config/
  companies.json    → Company + aggregator source list
  pending_review.json → Companies flagged for manual review (v9)
  settings.py       → Env-driven settings
```

### Data flow

```
Scrape → Normalise → Location Filter → Role Filter → LLM Check → Dedup → DB → Email
```

---

## Adding a New Company

For Greenhouse/Lever/Ashby-hosted companies, just add a row to `config/companies.json`:

```json
{
  "name": "Razorpay",
  "ats_type": "greenhouse",
  "identifier": "razorpay",
  "location_priority": "india",
  "enabled": true
}
```

For aggregator sources (keyword-based search):

```json
{
  "name": "Naukri - AI Jobs Pune",
  "ats_type": "naukri",
  "identifier": "data scientist,ml engineer",
  "search_location": "pune",
  "enabled": true
}
```

---

## Roles Tracked

### Data Science / AI-ML
- Data Scientist / Data Science
- Machine Learning Engineer / MLE
- AI Engineer / Applied Scientist
- GenAI / Gen-AI / LLM / NLP
- Data Analyst / Analytics Engineer
- MLOps / AI Research
- Deep Learning / Computer Vision

### Software Development (v3)
- Software Engineer / SDE / SDE-1 / SDE-2
- Backend Engineer / Backend Developer
- Frontend Engineer / Frontend Developer
- Full-stack / Fullstack
- Mobile / Android / iOS Developer
- DevOps / Cloud / Platform Engineer

---

## Companies & Sources (v3)

| Source | Type | Count |
|---|---|---|
| Phase 1 companies (ATS + custom) | Direct scrape | 10 |
| Phase 2 companies (pulled forward) | Greenhouse/Lever | 18 |
| Naukri.com | Aggregator | 2 configs |
| Instahyre | Aggregator | 1 |
| Cutshort | Aggregator | 1 |
| Wellfound (AngelList) | Aggregator | 1 |
| **Total sources** | | **33** |

> **Note:** LinkedIn is intentionally skipped — scraping violates their ToS and they actively block scrapers. A separate LinkedIn module can be added if a legitimate API path opens up.

---

## Running Tests

```bash
# Unit tests only (no network, no API keys needed)
pytest tests/ -v

# With integration tests (hits live APIs)
INTEGRATION=1 pytest tests/ -v
```

---

## Scheduling Options

### Option A: GitHub Actions (recommended — no server needed)
1. Push this repo to GitHub
2. Add secrets in Settings → Secrets and variables → Actions:
   - `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO`, `GOOGLE_API_KEY`
3. The workflow in `.github/workflows/run_agent.yml` runs every 6 hours

### Option B: Local APScheduler
```bash
python -m scheduler.run --mode scheduled
```
Keeps running in the terminal, fires every `RUN_INTERVAL_HOURS` hours (default: 6).

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `SMTP_USER` | SMTP username (e.g. Gmail address) | Yes |
| `SMTP_PASS` | SMTP password (Gmail App Password) | Yes |
| `ALERT_EMAIL_TO` | Recipient email(s), comma-separated | Yes |
| `SMTP_HOST` | SMTP server hostname | No (default: smtp.gmail.com) |
| `SMTP_PORT` | SMTP port | No (default: 587) |
| `GOOGLE_API_KEY` | Gemini API key (free tier) | Recommended |
| `RUN_INTERVAL_HOURS` | Pipeline run frequency | No (default: 6) |
| `DRY_RUN` | Skip DB writes and notifications | No (default: false) |
| `NOTIFY_ENABLED` | Enable/disable notifications | No (default: true) |
| `LOG_LEVEL` | Logging verbosity | No (default: INFO) |

---

## Notification Format (Email)

```
🚀 New Job Opening

Company:    Persistent Systems
Role:       Machine Learning Engineer
Location:   Pune
Source:     Company careers page
Link:       https://...
First seen: 2026-07-09 14:32 IST
```

---

## Per-Run Summary

Each pipeline run logs a detailed summary:

```
╔═══ RUN SUMMARY ═══╗
║ Sources scraped:         33
║ Total jobs fetched:     847
║ After location filter:  312
║ After role filter:       89
║ After LLM check:         72
║ New (unseen) jobs:       15
║ Notified:               15
║ Errors:                  2
║ Duration:            45.2s
╚══════════════════════════════╝
```

---

## Dashboard

### Run locally

```bash
streamlit run dashboard/app.py
```

The dashboard opens in your browser at `http://localhost:8501`. It reads from the same `database/jobs.db` used by the pipeline.

### Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (GitHub Actions already owns the live `jobs.db` via Change 16).
2. Go to [share.streamlit.io](https://share.streamlit.io), connect your GitHub repo.
3. Set **Main file path** to `ai-job-hunter/dashboard/app.py`.
4. The dashboard will auto-refresh when `jobs.db` is updated by the scheduled pipeline.

---

## Startup Discovery

Run the discovery script manually or weekly to find new Pune/India tech companies:

```bash
# Default search queries
python -m scripts.discover_startups

# Custom search
python -m scripts.discover_startups --search "ai startups pune 2026"

# Dry run (no file modifications)
python -m scripts.discover_startups --dry-run
```

ATS-hosted companies are auto-added to `config/companies.json`. Others are flagged in `config/pending_review.json`.

---

## Future Enhancements

- Resume matching / match score against your profile
- LinkedIn integration (when/if legitimate API access available)
- Phase 3 company expansion (100+ companies)
