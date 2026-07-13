"""
scrapers/custom/browserstack.py
Custom scraper for BrowserStack careers.
BrowserStack uses Workday ATS.
Workday URL: https://browserstack.wd1.myworkdayjobs.com/en-US/browserstack
"""

from __future__ import annotations

import logging
import time

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class BrowserStackScraper(BaseScraper):
    """
    BrowserStack careers via Workday ATS public API.
    """

    def __init__(self):
        super().__init__("BrowserStack", "browserstack")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/BrowserStack] Starting Workday API fetch")
        all_jobs = []
        
        # Workday subdomains can shift, try both wd1 and wd3
        subdomains = ["wd1", "wd3"]
        success = False

        for sub in subdomains:
            url = f"https://browserstack.{sub}.myworkdayjobs.com/wday/cxs/browserstack/browserstack/jobs"
            logger.info("[Custom/BrowserStack] Trying subdomain %s", sub)
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
                        logger.warning("[Custom/BrowserStack] Subdomain %s returned status %d", sub, resp.status_code)
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
                    logger.warning("[Custom/BrowserStack] Request to %s failed: %s", url, exc)
                    break
            
            if success and temp_jobs:
                all_jobs = temp_jobs
                logger.info("[Custom/BrowserStack] Successfully fetched %d jobs from subdomain %s", len(all_jobs), sub)
                break

        results = []
        for job in all_jobs:
            external_path = job.get("externalPath", "")
            # Default to wd1 but keep it flexible
            url = (
                f"https://browserstack.wd1.myworkdayjobs.com/en-US/browserstack{external_path}"
                if external_path
                else "https://www.browserstack.com/company/careers"
            )
            results.append(RawJob(
                company="BrowserStack",
                title=job.get("title", ""),
                location=job.get("locationsText", "") or job.get("primaryLocation", ""),
                url=url,
                posted_date=job.get("postedOn"),
                ats_type="custom",
                raw_data=job,
            ))
        return results
