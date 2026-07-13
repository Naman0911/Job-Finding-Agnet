"""
ashby.py
Scrapes Ashby-hosted job boards via their public JSON API.
Ashby exposes:
  POST https://api.ashbyhq.com/posting-api/job-board/{companyIdentifier}
  with JSON body: {"limit": 100, "page": 1}
"""

from __future__ import annotations

import logging
import time

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{company}"


class AshbyScraper(BaseScraper):
    """
    Generic Ashby scraper.

    Example:
        AshbyScraper("Sarvam AI", "sarvam-ai")
    """

    def __init__(self, company_name: str, identifier: str, request_delay: float = 1.0):
        super().__init__(company_name, identifier)
        self.request_delay = request_delay

    def fetch(self) -> list[RawJob]:
        url = ASHBY_API.format(company=self.identifier)
        logger.info("[Ashby] Fetching %s from %s", self.company_name, url)

        all_jobs: list[dict] = []
        page = 1
        while True:
            try:
                resp = requests.post(
                    url,
                    json={"limit": 100, "page": page},
                    timeout=30,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "AI-JobHunter/1.0 (job-monitoring-bot)",
                    },
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error("[Ashby] %s — request failed: %s", self.company_name, exc)
                break

            time.sleep(self.request_delay)

            try:
                data = resp.json()
            except ValueError as exc:
                logger.error("[Ashby] %s — JSON parse error: %s", self.company_name, exc)
                break

            jobs_page = data.get("results", [])
            all_jobs.extend(jobs_page)

            # Ashby uses moreDataAvailable or similar flag
            if not data.get("moreDataAvailable", False) or not jobs_page:
                break
            page += 1

        logger.info("[Ashby] %s — %d total jobs collected", self.company_name, len(all_jobs))

        results: list[RawJob] = []
        for job in all_jobs:
            location = self._extract_location(job)
            snippet = self._extract_snippet(job)
            results.append(
                RawJob(
                    company=self.company_name,
                    title=job.get("title", ""),
                    location=location,
                    url=job.get("jobUrl", ""),
                    posted_date=job.get("publishedDate"),
                    department=job.get("departmentName"),
                    description_snippet=snippet,
                    ats_type="ashby",
                    raw_data=job,
                )
            )
        return results

    # ---- helpers ----

    @staticmethod
    def _extract_location(job: dict) -> str:
        loc = job.get("location", "")
        if loc:
            return loc
        # Fallback: secondaryLocations list
        secondary = job.get("secondaryLocations", [])
        if secondary:
            return ", ".join(s.get("location", "") for s in secondary if s.get("location"))
        return ""

    @staticmethod
    def _extract_snippet(job: dict, max_chars: int = 500) -> str:
        import re
        desc = job.get("descriptionHtml", "") or job.get("description", "") or ""
        text = re.sub(r"<[^>]+>", " ", desc)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
