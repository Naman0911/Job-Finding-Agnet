"""
scrapers/custom/fractal.py
Custom scraper for Fractal Analytics.
Fractal uses Workday ATS at: https://fractal.wd1.myworkdayjobs.com/Fractal_Careers
We use the Workday public jobs API.
"""

from __future__ import annotations

import logging
import time

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class FractalScraper(BaseScraper):
    """
    Scraper for Fractal Analytics (Workday ATS).
    Workday exposes a JSON search endpoint at:
      POST /wday/cxs/{tenant}/{board}/jobs
    """

    def __init__(self):
        super().__init__("Fractal Analytics", "fractal")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Fractal] Starting Workday API fetch")
        all_jobs = []
        
        # Workday subdomains can shift, try both wd3 and wd1 (wd3 is currently active for Fractal)
        subdomains = ["wd3", "wd1"]
        success = False

        for sub in subdomains:
            url = f"https://fractal.{sub}.myworkdayjobs.com/wday/cxs/fractal/Fractal/jobs"
            logger.info("[Custom/Fractal] Trying subdomain %s", sub)
            offset = 0
            limit = 20
            temp_jobs = []

            while True:
                try:
                    resp = requests.post(
                        url,
                        json={
                            "appliedFacets": {},
                            "limit": limit,
                            "offset": offset,
                            "searchText": "",
                        },
                        timeout=15,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "application/json, text/plain, */*",
                            "Accept-Language": "en-US,en;q=0.9",
                        },
                    )
                    if resp.status_code != 200:
                        logger.warning("[Custom/Fractal] Subdomain %s returned status %d", sub, resp.status_code)
                        break
                    
                    data = resp.json()
                    postings = data.get("jobPostings", [])
                    temp_jobs.extend(postings)
                    total = data.get("total", 0)

                    if offset + limit >= total or not postings:
                        success = True
                        break
                    offset += limit
                    time.sleep(1)
                except Exception as exc:
                    logger.warning("[Custom/Fractal] Request to %s failed: %s", url, exc)
                    break
            
            if success and temp_jobs:
                all_jobs = temp_jobs
                logger.info("[Custom/Fractal] Successfully fetched %d jobs from subdomain %s", len(all_jobs), sub)
                break

        results = []
        for job in all_jobs:
            location = self._extract_location(job)
            external_path = job.get("externalPath", "")
            url = f"https://fractal.wd3.myworkdayjobs.com/en-US/Fractal{external_path}" if external_path else "https://fractal.wd3.myworkdayjobs.com/en-US/Fractal"
            results.append(RawJob(
                company="Fractal Analytics",
                title=job.get("title", ""),
                location=location,
                url=url,
                posted_date=job.get("postedOn"),
                ats_type="custom",
                raw_data=job,
            ))
        return results

    @staticmethod
    def _extract_location(job: dict) -> str:
        locs = job.get("locationsText", "") or ""
        if locs:
            return locs
        primary = job.get("primaryLocation", "")
        return primary
