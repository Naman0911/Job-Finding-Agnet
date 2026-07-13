# AI Job Hunter 🤖

An autonomous agent that monitors company career pages and job aggregators (Indeed, Glassdoor, Naukri, Instahyre, Wellfound, Cutshort) for **Data Science, AI/ML, and Software Engineering** roles.

It actively filters for entry-level/fresher roles, deduplicates alerts, stores them in a local SQLite database, and runs entirely in the background via GitHub Actions.

## ✨ Key Features

- **Automated Scheduling**: Runs automatically every 8 hours via GitHub Actions. State is persisted by automatically committing the SQLite database back to the repo.
- **Streamlit Dashboard**: A local web interface to browse jobs, filter by company/source, view analytics, and manage tracked companies.
- **Multi-Stage Filtering Pipeline**:
  - *Location Filter*: Targets jobs specifically in Pune and across India.
  - *Role Keyword Filter*: Whitelists 30+ variations of SDE, DS, ML, GenAI, and DevOps roles.
  - *Experience Filter*: Explicitly targets fresher/entry-level jobs and rejects senior/managerial roles.
  - *Semantic Relevance (Local)*: Uses `sentence-transformers` (`all-MiniLM-L6-v2`) to filter out irrelevant roles locally, saving LLM costs.
  - *LLM Classification*: Uses Google's Gemini Flash for a final, high-accuracy context check on the job title.
- **Smart Startup Discovery**: Includes a standalone script (`discover_startups.py`) that scans Google News for recently funded startups, detects their ATS platform, and cues them up for tracking.
- **Email Digests**: Sends a clean, consolidated email digest of new jobs after every successful run.

## 🚀 Quick Start

### 1. Install dependencies

```bash
cd ai-job-hunter
pip install -r requirements.txt
playwright install chromium   # Required for JS-rendered career pages
```

> **Note**: On the first run, the agent will download the `all-MiniLM-L6-v2` model weights (~80MB) for local semantic classification.

### 2. Configure Credentials

```bash
cp .env.example .env
```
Edit the `.env` file with your details:
- `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` (Use a Gmail App Password)
- `GOOGLE_API_KEY` (Free from Google AI Studio)

### 3. Run the Pipeline

```bash
# Production run (saves to DB and sends email)
python -m scheduler.run --mode once

# Dry run (fetches jobs but doesn't save or notify)
python -m scheduler.run --mode dry-run
```

## 📊 Streamlit Dashboard

You can explore your tracked jobs visually:
```bash
streamlit run dashboard/app.py
```
This opens a local web app at `http://localhost:8501` where you can view charts, filter active roles, and launch one-click application links.

## 🔍 Startup Discovery

Automatically hunt for new tech startups to track:
```bash
# Default search (Pune tech startups)
python -m scripts.discover_startups

# Custom search query
python -m scripts.discover_startups --search "ai startups india seed funding"
```
Companies with recognized ATS platforms are auto-added to `config/companies.json`. Others are flagged in `config/pending_review.json` for manual addition.

## 🏗️ Architecture

```
scrapers/           → API scrapers (Greenhouse, Lever, Ashby) + HTML Aggregators
pipeline/           → The 7-stage filtering and deduplication pipeline
dashboard/          → Streamlit UI app
scripts/            → Standalone tools (startup discovery)
database/           → SQLite storage (jobs + run logs)
notifier/           → Email digest generation
config/             → Managed lists of tracked companies and environment settings
```

## ⚙️ Automated Deployment (GitHub Actions)

You do not need a server to run this continuously.
1. Push this repository to GitHub.
2. Go to **Settings → Secrets and variables → Actions** in your GitHub Repo.
3. Add your environment variables as Repository Secrets (`SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO`, `GOOGLE_API_KEY`).
4. The workflow in `.github/workflows/run_agent.yml` will automatically wake up every 8 hours, scrape for jobs, and push the updated database back to your repository.
