"""
database/db.py
SQLite wrapper for the AI Job Hunter agent.

v3 changes:
  - INSERT now includes `source` column
  - Added migration support for adding `source` column to existing DBs

Usage:
    from database.db import JobDatabase

    with JobDatabase() as db:
        db.insert_job(job_dict)
        new_jobs = db.get_unnotified_jobs()
        db.mark_notified([job_id1, job_id2])
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database.models import ALL_DDL, MIGRATIONS

logger = logging.getLogger(__name__)

# Default DB path — sits next to this file
DEFAULT_DB_PATH = Path(__file__).parent / "jobs.db"


class JobDatabase:
    """
    Thread-safe SQLite wrapper with context manager support.

    All public methods accept / return plain dicts so the rest of
    the codebase never has to touch sqlite3 directly.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "JobDatabase":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # don't suppress exceptions

    # ── Connection management ──────────────────────────────────────────────────

    def connect(self):
        logger.debug("[DB] Connecting to %s", self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._create_tables()
        self._run_migrations()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("[DB] Connection closed")

    # ── Quota tracking ────────────────────────────────────────────────────────

    def increment_llm_calls(self, count: int = 1) -> int:
        """Increment the LLM API call counter for today, and return the new total."""
        self._conn_required()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self._conn.execute(
            """
            INSERT INTO api_quota (date, calls)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET calls = calls + ?
            """,
            (today, count, count)
        )
        self._conn.commit()
        return self.get_llm_calls_today()

    def get_llm_calls_today(self) -> int:
        """Get the total LLM API calls made today."""
        self._conn_required()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur = self._conn.execute("SELECT calls FROM api_quota WHERE date = ?", (today,))
        row = cur.fetchone()
        return row["calls"] if row else 0

    def _conn_required(self):
        if self._conn is None:
            raise RuntimeError("JobDatabase not connected. Use 'with JobDatabase() as db:'")

    def _create_tables(self):
        cur = self._conn.cursor()
        for ddl in ALL_DDL:
            cur.execute(ddl)
        self._conn.commit()

    def _run_migrations(self):
        """Run schema migrations (safe to re-run — uses IF NOT EXISTS / try-except)."""
        for migration_sql in MIGRATIONS:
            try:
                self._conn.execute(migration_sql)
                self._conn.commit()
                logger.debug("[DB] Migration applied: %s", migration_sql[:60])
            except sqlite3.OperationalError:
                # Column/table already exists — that's fine
                pass

    # ── Write operations ───────────────────────────────────────────────────────

    def insert_job(self, job: dict) -> Optional[int]:
        """
        Insert a normalised job dict.  Silently ignores duplicates
        (UNIQUE constraint on dedup_hash).

        Returns the rowid of the inserted row, or None on duplicate.
        """
        self._conn_required()
        sql = """
            INSERT OR IGNORE INTO jobs
                (company, title, location, url, posted_date, first_seen_at,
                 dedup_hash, notified, department, description_snippet, ats_type, source)
            VALUES
                (:company, :title, :location, :url, :posted_date, :first_seen_at,
                 :dedup_hash, :notified, :department, :description_snippet, :ats_type, :source)
        """
        cur = self._conn.execute(sql, job)
        self._conn.commit()
        if cur.lastrowid and cur.rowcount > 0:
            logger.debug("[DB] Inserted job id=%d  %r @ %s", cur.lastrowid, job["title"], job["company"])
            return cur.lastrowid
        return None

    def insert_jobs(self, jobs: list[dict]) -> int:
        """Bulk insert. Returns count of actually inserted rows."""
        self._conn_required()
        inserted = 0
        for job in jobs:
            row_id = self.insert_job(job)
            if row_id:
                inserted += 1
        logger.info("[DB] Bulk insert: %d inserted / %d total", inserted, len(jobs))
        return inserted

    def mark_notified(self, job_ids: list[int]):
        """Mark a list of job IDs as notified."""
        self._conn_required()
        if not job_ids:
            return
        placeholders = ",".join("?" * len(job_ids))
        self._conn.execute(
            f"UPDATE jobs SET notified=1 WHERE id IN ({placeholders})",
            job_ids,
        )
        self._conn.commit()
        logger.debug("[DB] Marked %d jobs as notified", len(job_ids))

    # ── Read operations ────────────────────────────────────────────────────────

    def get_seen_hashes(self) -> set[str]:
        """Return the complete set of known dedup_hashes (for fast lookups)."""
        self._conn_required()
        cur = self._conn.execute("SELECT dedup_hash FROM jobs")
        return {row[0] for row in cur.fetchall()}

    def get_unnotified_jobs(self) -> list[dict]:
        """Return all jobs that have been inserted but not yet notified."""
        self._conn_required()
        cur = self._conn.execute(
            "SELECT * FROM jobs WHERE notified=0 ORDER BY first_seen_at ASC"
        )
        return [dict(row) for row in cur.fetchall()]

    def get_all_jobs(self, limit: int = 500) -> list[dict]:
        """Return most recent jobs (for dashboard / debugging)."""
        self._conn_required()
        cur = self._conn.execute(
            "SELECT * FROM jobs ORDER BY first_seen_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_stats(self) -> dict:
        """Return summary statistics."""
        self._conn_required()
        cur = self._conn.execute(
            "SELECT COUNT(*) as total, SUM(notified) as notified FROM jobs"
        )
        row = dict(cur.fetchone())
        return {
            "total_jobs": row.get("total", 0),
            "notified": row.get("notified", 0),
            "pending_notification": (row.get("total", 0) or 0) - (row.get("notified", 0) or 0),
        }

    # ── Run log ────────────────────────────────────────────────────────────────

    def log_run_start(self) -> int:
        """Insert a new run_log row and return its ID."""
        self._conn_required()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO run_log (started_at) VALUES (?)", (now,)
        )
        self._conn.commit()
        return cur.lastrowid

    def log_run_end(self, run_id: int, **kwargs):
        """Update a run_log row with completion details."""
        self._conn_required()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            """UPDATE run_log SET finished_at=?, companies_count=?,
               jobs_scraped=?, jobs_new=?, jobs_notified=?, errors=?
               WHERE id=?""",
            (
                now,
                kwargs.get("companies_count", 0),
                kwargs.get("jobs_scraped", 0),
                kwargs.get("jobs_new", 0),
                kwargs.get("jobs_notified", 0),
                kwargs.get("errors", ""),
                run_id,
            ),
        )
        self._conn.commit()
