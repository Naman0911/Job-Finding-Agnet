"""
greenhouse.py
Scrapes Greenhouse-hosted job boards via their public JSON API.
No scraping required — Greenhouse exposes:
  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseScraper(BaseScraper):
    """
    Generic Greenhouse scraper — works for any company with a Greenhouse board.
    Pass the company's Greenhouse slug as `identifier`.

    Example:
        GreenhouseScraper("Postman", "postman")
        GreenhouseScraper("Chargebee", "chargebee")
    """

    def __init__(self, company_name: str, identifier: str, request_delay: float = 1.0):
        super().__init__(company_name, identifier)
        self.request_delay = request_delay
        self.ats_type = "greenhouse"

    def fetch(self) -> list[RawJob]:
        url = GREENHOUSE_API.format(slug=self.identifier)
        logger.info("[Greenhouse] Fetching %s from %s", self.company_name, url)

        try:
            resp = requests.get(
                url,
                params={"content": "true"},
                timeout=30,
                headers={"User-Agent": "AI-JobHunter/1.0 (job-monitoring-bot)"},
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[Greenhouse] %s — request failed: %s", self.company_name, exc)
            return []

        time.sleep(self.request_delay)  # be polite

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error("[Greenhouse] %s — JSON parse error: %s", self.company_name, exc)
            return []

        jobs_raw = data.get("jobs", [])
        logger.info("[Greenhouse] %s — %d total jobs returned", self.company_name, len(jobs_raw))

        results: list[RawJob] = []
        for job in jobs_raw:
            location = self._extract_location(job)
            description_snippet = self._extract_snippet(job)
            results.append(
                RawJob(
                    company=self.company_name,
                    title=job.get("title", ""),
                    location=location,
                    url=job.get("absolute_url", ""),
                    posted_date=job.get("updated_at"),
                    department=self._extract_department(job),
                    description_snippet=description_snippet,
                    ats_type="greenhouse",
                    raw_data=job,
                )
            )
        return results

    # ---- helpers ----

    @staticmethod
    def _extract_location(job: dict) -> str:
        """
        Greenhouse jobs may have location as:
          - job["location"]["name"]  (single-location listing)
          - job["offices"][0]["name"] (if location is missing)
        """
        loc = job.get("location", {})
        if isinstance(loc, dict) and loc.get("name"):
            return loc["name"]
        offices = job.get("offices", [])
        if offices:
            names = [o.get("name", "") for o in offices if o.get("name")]
            return ", ".join(names)
        return ""

    @staticmethod
    def _extract_department(job: dict) -> Optional[str]:
        departments = job.get("departments", [])
        if departments:
            return departments[0].get("name", "")
        return None

    @staticmethod
    def _extract_snippet(job: dict, max_chars: int = 500) -> Optional[str]:
        """Return first max_chars of the job body (HTML stripped)."""
        content = job.get("content", "") or ""
        # Strip HTML tags naively for snippet
        import re
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] if text else None
