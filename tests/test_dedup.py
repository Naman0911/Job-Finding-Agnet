"""
tests/test_dedup.py
Tests for the database, normalizer, and dedup pipeline stages.
Uses an in-memory SQLite database (no file I/O).
"""

import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from database.db import JobDatabase
from pipeline.normalizer import normalise, _make_hash
from pipeline.dedup import filter_new_jobs
from scrapers.base_scraper import RawJob


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Return a fresh JobDatabase backed by a temp file."""
    db_path = tmp_path / "test_jobs.db"
    db = JobDatabase(db_path)
    db.connect()
    yield db
    db.close()


def make_raw_job(**kwargs) -> RawJob:
    defaults = dict(
        company="TestCo",
        title="Data Scientist",
        location="Pune, India",
        url="https://example.com/job/1",
        posted_date="2026-01-01",
        ats_type="greenhouse",
    )
    defaults.update(kwargs)
    return RawJob(**defaults)


def make_normalised(**kwargs) -> dict:
    return normalise(make_raw_job(**kwargs))


# ── Normaliser tests ──────────────────────────────────────────────────────────

class TestNormaliser:

    def test_basic_normalisation(self):
        raw = make_raw_job()
        job = normalise(raw)
        assert job["company"] == "TestCo"
        assert job["title"] == "Data Scientist"
        assert job["location"] == "Pune, India"
        assert "dedup_hash" in job
        assert len(job["dedup_hash"]) == 64  # SHA-256 hex

    def test_whitespace_stripped(self):
        raw = make_raw_job(title="  Data  Scientist  ", company="  TestCo  ")
        job = normalise(raw)
        assert job["title"] == "Data Scientist"
        assert job["company"] == "TestCo"

    def test_hash_deterministic(self):
        raw1 = make_raw_job()
        raw2 = make_raw_job()
        assert normalise(raw1)["dedup_hash"] == normalise(raw2)["dedup_hash"]

    def test_hash_differs_on_title_change(self):
        raw1 = make_raw_job(title="Data Scientist")
        raw2 = make_raw_job(title="ML Engineer")
        assert normalise(raw1)["dedup_hash"] != normalise(raw2)["dedup_hash"]

    def test_iso_date_normalisation(self):
        raw = make_raw_job(posted_date="2026-07-09T14:32:00Z")
        job = normalise(raw)
        assert job["posted_date"] == "2026-07-09"

    def test_epoch_ms_date_normalisation(self):
        raw = make_raw_job(posted_date="1720518720000")  # some epoch ms
        job = normalise(raw)
        assert len(job["posted_date"]) == 10  # YYYY-MM-DD

    def test_first_seen_at_is_set(self):
        job = make_normalised()
        assert "first_seen_at" in job
        assert "T" in job["first_seen_at"]  # ISO format


# ── Database tests ────────────────────────────────────────────────────────────

class TestDatabase:

    def test_insert_and_retrieve(self, tmp_db):
        job = make_normalised()
        row_id = tmp_db.insert_job(job)
        assert row_id is not None

        jobs = tmp_db.get_all_jobs()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Data Scientist"

    def test_duplicate_ignored(self, tmp_db):
        job = make_normalised()
        id1 = tmp_db.insert_job(job)
        id2 = tmp_db.insert_job(job)  # same hash
        assert id1 is not None
        assert id2 is None  # duplicate → None

        jobs = tmp_db.get_all_jobs()
        assert len(jobs) == 1

    def test_get_seen_hashes(self, tmp_db):
        job = make_normalised()
        tmp_db.insert_job(job)
        hashes = tmp_db.get_seen_hashes()
        assert job["dedup_hash"] in hashes

    def test_mark_notified(self, tmp_db):
        job = make_normalised()
        row_id = tmp_db.insert_job(job)
        
        unnotified = tmp_db.get_unnotified_jobs()
        assert len(unnotified) == 1

        tmp_db.mark_notified([row_id])
        
        unnotified_after = tmp_db.get_unnotified_jobs()
        assert len(unnotified_after) == 0

    def test_stats(self, tmp_db):
        job1 = make_normalised(title="Data Scientist")
        job2 = make_normalised(title="ML Engineer", url="https://example.com/job/2")
        tmp_db.insert_job(job1)
        id2 = tmp_db.insert_job(job2)
        tmp_db.mark_notified([id2])

        stats = tmp_db.get_stats()
        assert stats["total_jobs"] == 2
        assert stats["notified"] == 1
        assert stats["pending_notification"] == 1

    def test_run_log(self, tmp_db):
        run_id = tmp_db.log_run_start()
        assert run_id is not None
        tmp_db.log_run_end(run_id, jobs_scraped=50, jobs_new=3, jobs_notified=3)


# ── Dedup filter tests ────────────────────────────────────────────────────────

class TestDedup:

    def test_all_new_jobs_pass(self, tmp_db):
        jobs = [
            make_normalised(title="Data Scientist"),
            make_normalised(title="ML Engineer", url="https://example.com/2"),
        ]
        new = filter_new_jobs(jobs, tmp_db)
        assert len(new) == 2

    def test_seen_jobs_filtered(self, tmp_db):
        job = make_normalised()
        tmp_db.insert_job(job)

        # Same job again
        result = filter_new_jobs([job], tmp_db)
        assert len(result) == 0

    def test_mixed_new_and_seen(self, tmp_db):
        old_job = make_normalised(title="Old Job")
        new_job = make_normalised(title="New Job", url="https://example.com/new")
        tmp_db.insert_job(old_job)

        result = filter_new_jobs([old_job, new_job], tmp_db)
        assert len(result) == 1
        assert result[0]["title"] == "New Job"

    def test_empty_input(self, tmp_db):
        assert filter_new_jobs([], tmp_db) == []

    def test_running_twice_no_duplicates(self, tmp_db):
        """Core dedup property: running the same jobs twice inserts nothing the 2nd time."""
        jobs = [make_normalised(title=f"Job {i}", url=f"https://example.com/{i}")
                for i in range(5)]

        # First run
        new_first = filter_new_jobs(jobs, tmp_db)
        assert len(new_first) == 5
        tmp_db.insert_jobs(new_first)

        # Second run — nothing should be new
        new_second = filter_new_jobs(jobs, tmp_db)
        assert len(new_second) == 0
