"""
scrapers/custom/persistent.py
Custom Playwright scraper for Persistent Systems careers page.
URL: https://www.persistent.com/careers/current-openings/

Persistent uses iCIMS ATS — jobs are loaded via embedded iframe or XHR.
This scraper falls back to fetching the known iCIMS API endpoint directly.
"""

from __future__ import annotations

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class PersistentScraper(BaseScraper):
    """
    Scraper for Persistent Systems.
    Strategy: attempt iCIMS API first; if that fails, fall back to Playwright.
    """

    ICIMS_URL = "https://careers.persistent.com/jobs/search"
    FALLBACK_URL = "https://www.persistent.com/careers/current-openings/"

    def __init__(self):
        super().__init__("Persistent Systems", "https://www.persistent.com/careers/")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Persistent] Starting fetch")

        # Try direct iCIMS-style API first
        jobs = self._fetch_via_api()
        if jobs:
            return jobs

        # Fallback: Playwright
        return self._fetch_via_playwright()

    def _fetch_via_api(self) -> list[RawJob]:
        """
        Persistent's careers are often served via Naukri / their own portal.
        We try a known structured endpoint and parse JSON if available.
        """
        try:
            resp = requests.get(
                "https://careers.persistent.com/api/jobs",
                params={"location": "India", "limit": 200},
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 AI-JobHunter/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs_raw = data if isinstance(data, list) else data.get("jobs", [])
                if jobs_raw:
                    logger.info("[Custom/Persistent] Got %d jobs from API", len(jobs_raw))
                    return self._parse_api_jobs(jobs_raw)
        except Exception as exc:
            logger.debug("[Custom/Persistent] API attempt failed: %s", exc)

        return []

    def _parse_api_jobs(self, jobs_raw: list) -> list[RawJob]:
        results = []
        for job in jobs_raw:
            results.append(RawJob(
                company="Persistent Systems",
                title=job.get("title", job.get("jobTitle", "")),
                location=job.get("location", job.get("city", "")),
                url=job.get("url", job.get("applyUrl", self.FALLBACK_URL)),
                posted_date=job.get("postedDate", job.get("datePosted")),
                description_snippet=str(job.get("description", ""))[:500],
                ats_type="custom",
                raw_data=job,
            ))
        return results

    def _fetch_via_playwright(self) -> list[RawJob]:
        """
        Fall back to Playwright rendering for the careers listing page.
        Requires playwright to be installed: pip install playwright && playwright install chromium
        """
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        except ImportError:
            logger.error("[Custom/Persistent] Playwright not installed — skipping")
            return []

        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            try:
                page.goto(self.FALLBACK_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)
                html = page.content()
                jobs = self._parse_html(html)
                logger.info("[Custom/Persistent] Playwright got %d jobs", len(jobs))
            except PlaywrightTimeout:
                logger.error("[Custom/Persistent] Playwright timed out")
            except Exception as exc:
                logger.error("[Custom/Persistent] Playwright error: %s", exc)
            finally:
                browser.close()

        return jobs

    def _parse_html(self, html: str) -> list[RawJob]:
        """Parse generic job listings from rendered HTML."""
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Generic strategy: find anchor tags containing "job" with title-like text
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            if not re.search(r"/job|/career|/opening|/position", href, re.I):
                continue

            url = href if href.startswith("http") else f"https://www.persistent.com{href}"
            jobs.append(RawJob(
                company="Persistent Systems",
                title=text,
                location="India",  # assume India if can't determine
                url=url,
                ats_type="custom",
            ))

        return jobs
