"""
database/models.py
SQLite table creation DDL for the AI Job Hunter agent.

Tables:
  jobs        — every job we've ever seen and decided is relevant
  run_log     — one row per pipeline run (for diagnostics)

v3 changes:
  - Added `source` column to jobs table (tracks which site/platform a job came from)

v5 changes:
  - Added `api_quota` table to track daily Gemini API calls
"""

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    location        TEXT    NOT NULL DEFAULT '',
    url             TEXT    NOT NULL DEFAULT '',
    posted_date     TEXT    DEFAULT '',
    first_seen_at   TEXT    NOT NULL,
    dedup_hash      TEXT    NOT NULL UNIQUE,
    notified        INTEGER NOT NULL DEFAULT 0,
    department      TEXT    DEFAULT '',
    description_snippet TEXT DEFAULT '',
    ats_type        TEXT    DEFAULT 'unknown',
    source          TEXT    DEFAULT 'Company careers page'
);
"""

CREATE_HASH_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_dedup_hash ON jobs(dedup_hash);
"""

CREATE_RUN_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    companies_count INTEGER DEFAULT 0,
    jobs_scraped    INTEGER DEFAULT 0,
    jobs_new        INTEGER DEFAULT 0,
    jobs_notified   INTEGER DEFAULT 0,
    errors          TEXT    DEFAULT ''
);
"""

# Migration: add source column to existing databases that don't have it yet
ADD_SOURCE_COLUMN = """
ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'Company careers page';
"""

CREATE_API_QUOTA_TABLE = """
CREATE TABLE IF NOT EXISTS api_quota (
    date TEXT PRIMARY KEY,
    calls INTEGER DEFAULT 0
);
"""

ALL_DDL = [
    CREATE_JOBS_TABLE,
    CREATE_HASH_INDEX,
    CREATE_RUN_LOG_TABLE,
    CREATE_API_QUOTA_TABLE,
]

MIGRATIONS = [
    ADD_SOURCE_COLUMN,
]
