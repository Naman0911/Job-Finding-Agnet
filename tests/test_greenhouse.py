"""
tests/test_greenhouse.py
Tests for the Greenhouse scraper (uses live API in integration tests).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock

from scrapers.greenhouse import GreenhouseScraper
from scrapers.base_scraper import RawJob


# ── Unit tests (mocked) ───────────────────────────────────────────────────────

class TestGreenhouseScraper:
    
    def test_extract_location_from_location_field(self):
        scraper = GreenhouseScraper("Test", "test")
        job = {"location": {"name": "Pune, India"}}
        assert scraper._extract_location(job) == "Pune, India"

    def test_extract_location_from_offices(self):
        scraper = GreenhouseScraper("Test", "test")
        job = {"location": {}, "offices": [{"name": "Bengaluru"}, {"name": "Pune"}]}
        result = scraper._extract_location(job)
        assert "Bengaluru" in result or "Pune" in result

    def test_extract_location_empty(self):
        scraper = GreenhouseScraper("Test", "test")
        job = {}
        assert scraper._extract_location(job) == ""

    def test_fetch_returns_raw_jobs(self):
        mock_response = {
            "jobs": [
                {
                    "title": "Data Scientist",
                    "location": {"name": "India"},
                    "absolute_url": "https://boards.greenhouse.io/test/jobs/123",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "departments": [{"name": "Data"}],
                    "content": "<p>We are looking for a Data Scientist.</p>",
                }
            ]
        }
        with patch("scrapers.greenhouse.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            scraper = GreenhouseScraper("TestCo", "testco")
            jobs = scraper.fetch()

        assert len(jobs) == 1
        assert isinstance(jobs[0], RawJob)
        assert jobs[0].title == "Data Scientist"
        assert jobs[0].location == "India"
        assert jobs[0].company == "TestCo"
        assert jobs[0].ats_type == "greenhouse"

    def test_fetch_handles_request_error(self):
        import requests as req
        with patch("scrapers.greenhouse.requests.get") as mock_get:
            mock_get.side_effect = req.RequestException("Connection refused")
            scraper = GreenhouseScraper("TestCo", "testco")
            jobs = scraper.fetch()
        assert jobs == []

    def test_fetch_handles_empty_response(self):
        with patch("scrapers.greenhouse.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": []}
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            scraper = GreenhouseScraper("TestCo", "testco")
            jobs = scraper.fetch()
        assert jobs == []

    def test_snippet_strips_html(self):
        scraper = GreenhouseScraper("Test", "test")
        job = {"content": "<h1>Hello</h1><p>We need <b>data scientists</b>.</p>"}
        snippet = scraper._extract_snippet(job)
        assert "<" not in snippet
        assert "Hello" in snippet
        assert "data scientists" in snippet


# ── Integration test (hits real API — skip in CI unless INTEGRATION=1) ────────

@pytest.mark.skipif(
    not __import__("os").environ.get("INTEGRATION"),
    reason="Set INTEGRATION=1 to run live API tests",
)
class TestGreenhouseIntegration:

    def test_postman_jobs_exist(self):
        """Postman should always have open jobs."""
        scraper = GreenhouseScraper("Postman", "postman")
        jobs = scraper.fetch()
        assert len(jobs) > 0, "Postman should have at least one open job"
        assert all(j.title for j in jobs), "All jobs should have a title"
        assert all(j.url for j in jobs), "All jobs should have a URL"

    def test_chargebee_jobs(self):
        scraper = GreenhouseScraper("Chargebee", "chargebee")
        jobs = scraper.fetch()
        print(f"\nChargebee: {len(jobs)} jobs")
        for j in jobs[:3]:
            print(f"  {j.title} | {j.location}")
        assert isinstance(jobs, list)
