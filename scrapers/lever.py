"""
lever.py
Scrapes Lever-hosted job boards via their public JSON API.
Lever exposes:
  https://api.lever.co/v0/postings/{company}?mode=json&limit=100

v3 changes:
  - Added full pagination support (walks all pages until no more results)
  - Increased limit from 250 to 100 per page with offset-based pagination
"""

from __future__ import annotations

import logging
import time

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

LEVER_API = "https://api.lever.co/v0/postings/{company}"


class LeverScraper(BaseScraper):
    """
    Generic Lever scraper — works for any company with a Lever board.
    v3: Full pagination support to ensure all jobs are captured.

    Example:
        LeverScraper("BrowserStack", "browserstack")
    """

    def __init__(self, company_name: str, identifier: str, request_delay: float = 1.0):
        super().__init__(company_name, identifier)
        self.request_delay = request_delay

    def fetch(self) -> list[RawJob]:
        url = LEVER_API.format(company=self.identifier)
        logger.info("[Lever] Fetching %s from %s", self.company_name, url)

        all_jobs: list[dict] = []
        offset = 0
        page_size = 100
        page_num = 0

        while True:
            page_num += 1
            try:
                params = {
                    "mode": "json",
                    "limit": page_size,
                }
                if offset > 0:
                    params["offset"] = offset

                resp = requests.get(
                    url,
                    params=params,
                    timeout=30,
                    headers={"User-Agent": "AI-JobHunter/1.0 (job-monitoring-bot)"},
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error("[Lever] %s — request failed: %s", self.company_name, exc)
                break

            time.sleep(self.request_delay)

            try:
                jobs_page = resp.json()
            except ValueError as exc:
                logger.error("[Lever] %s — JSON parse error: %s", self.company_name, exc)
                break

            if not isinstance(jobs_page, list):
                logger.warning("[Lever] %s — unexpected response shape", self.company_name)
                break

            if not jobs_page:
                logger.debug("[Lever] %s — no more results at page %d", self.company_name, page_num)
                break

            all_jobs.extend(jobs_page)
            logger.debug("[Lever] %s — page %d: %d jobs (total so far: %d)",
                         self.company_name, page_num, len(jobs_page), len(all_jobs))

            # If we got fewer than page_size, we've reached the end
            if len(jobs_page) < page_size:
                break

            offset += page_size

        logger.info("[Lever] %s — %d total jobs returned (%d pages)",
                    self.company_name, len(all_jobs), page_num)

        results: list[RawJob] = []
        for job in all_jobs:
            location = self._extract_location(job)
            snippet = self._extract_snippet(job)
            results.append(
                RawJob(
                    company=self.company_name,
                    title=job.get("text", ""),
                    location=location,
                    url=job.get("hostedUrl", ""),
                    posted_date=self._extract_date(job),
                    department=job.get("categories", {}).get("department"),
                    description_snippet=snippet,
                    ats_type="lever",
                    raw_data=job,
                )
            )
        return results

    # ---- helpers ----

    @staticmethod
    def _extract_location(job: dict) -> str:
        # Lever: categories.location OR lists[0].text where tag=="location"
        cats = job.get("categories", {})
        if cats.get("location"):
            return cats["location"]
        for tag_item in job.get("lists", []):
            if tag_item.get("text", "").lower().startswith("location"):
                return tag_item.get("content", "")
        return ""

    @staticmethod
    def _extract_date(job: dict) -> str:
        """Lever stores epoch milliseconds in 'createdAt'."""
        created = job.get("createdAt")
        if created:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc)
                return dt.isoformat()
            except (ValueError, OSError):
                return str(created)
        return ""

    @staticmethod
    def _extract_snippet(job: dict, max_chars: int = 500) -> str:
        import re
        desc = job.get("descriptionPlain", "") or job.get("description", "") or ""
        text = re.sub(r"<[^>]+>", " ", desc)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
