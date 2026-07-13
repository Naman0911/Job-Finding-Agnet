"""
scrapers/custom/freshworks.py
Custom scraper for Freshworks careers.
Freshworks uses their own SmartRecruiters-based system.
API: https://careers.freshworks.com/api/jobs
"""

from __future__ import annotations

import logging
import time

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class FreshworksScraper(BaseScraper):
    """
    Scraper for Freshworks career page.
    SmartRecruiters public API endpoint.
    """

    SMARTRECRUITERS_API = "https://api.smartrecruiters.com/v1/companies/Freshworks/postings"

    def __init__(self):
        super().__init__("Freshworks", "https://www.freshworks.com/company/careers/")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Freshworks] Starting fetch via SmartRecruiters")

        all_jobs = []
        offset = 0
        limit = 100

        while True:
            try:
                resp = requests.get(
                    self.SMARTRECRUITERS_API,
                    params={"limit": limit, "offset": offset},
                    timeout=30,
                    headers={"User-Agent": "AI-JobHunter/1.0"},
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error("[Custom/Freshworks] Request failed: %s", exc)
                break

            time.sleep(1)

            try:
                data = resp.json()
            except ValueError:
                logger.error("[Custom/Freshworks] JSON parse error")
                break

            content = data.get("content", [])
            all_jobs.extend(content)

            total = data.get("totalFound", 0)
            if offset + limit >= total or not content:
                break
            offset += limit

        logger.info("[Custom/Freshworks] %d total jobs fetched", len(all_jobs))

        results = []
        for job in all_jobs:
            location_obj = job.get("location", {})
            location = self._format_location(location_obj)
            results.append(RawJob(
                company="Freshworks",
                title=job.get("name", ""),
                location=location,
                url=f"https://jobs.smartrecruiters.com/Freshworks/{job.get('id', '')}",
                posted_date=job.get("releasedDate"),
                department=job.get("department", {}).get("label"),
                description_snippet=job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")[:500],
                ats_type="custom",
                raw_data=job,
            ))
        return results

    @staticmethod
    def _format_location(loc: dict) -> str:
        parts = []
        if loc.get("city"):
            parts.append(loc["city"])
        if loc.get("region"):
            parts.append(loc["region"])
        if loc.get("country"):
            parts.append(loc["country"])
        if loc.get("remote"):
            return "Remote"
        return ", ".join(parts)
