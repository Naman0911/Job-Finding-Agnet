"""
scrapers/custom/sarvam.py
Custom scraper for Sarvam AI.
Sarvam AI uses Ashby ATS. Their public job board URL is:
  https://jobs.ashbyhq.com/sarvam.ai
We use the Ashby public embed API directly.
"""

from __future__ import annotations

import logging
import json

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class SarvamScraper(BaseScraper):
    """
    Sarvam AI careers scraper.
    Uses the public Ashby job board embed endpoint.
    """

    # Ashby public embed API (no auth required)
    EMBED_URL = "https://jobs.ashbyhq.com/sarvam.ai"
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/sarvam.ai?includeCompensation=true"

    def __init__(self):
        super().__init__("Sarvam AI", "sarvam.ai")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Sarvam] Starting fetch")

        # Try the GET endpoint (some Ashby boards expose public GET)
        jobs = self._try_get_api()
        if jobs:
            return jobs

        # Fall back to scraping the embed page
        return self._scrape_embed_page()

    def _try_get_api(self) -> list[RawJob]:
        """Try Ashby's public board API with GET instead of POST."""
        try:
            resp = requests.get(
                self.API_URL,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 AI-JobHunter/1.0",
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs_raw = data.get("results", [])
                if jobs_raw:
                    logger.info("[Custom/Sarvam] Got %d jobs from Ashby GET API", len(jobs_raw))
                    return self._parse_ashby_jobs(jobs_raw)
        except Exception as exc:
            logger.debug("[Custom/Sarvam] GET API attempt failed: %s", exc)
        return []

    def _parse_ashby_jobs(self, jobs_raw: list) -> list[RawJob]:
        results = []
        for job in jobs_raw:
            loc = job.get("location", "") or ""
            results.append(RawJob(
                company="Sarvam AI",
                title=job.get("title", ""),
                location=loc,
                url=job.get("jobUrl", self.EMBED_URL),
                posted_date=job.get("publishedDate"),
                department=job.get("departmentName"),
                description_snippet=self._strip_html(job.get("descriptionHtml", ""))[:500],
                ats_type="custom",
                raw_data=job,
            ))
        return results

    def _scrape_embed_page(self) -> list[RawJob]:
        """Scrape the public Ashby job board HTML page."""
        logger.info("[Custom/Sarvam] Falling back to Ashby embed page scraping")
        try:
            resp = requests.get(
                self.EMBED_URL,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 AI-JobHunter/1.0"},
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[Custom/Sarvam] Embed page request failed: %s", exc)
            return self._playwright_fallback()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Ashby job boards often embed JSON in <script> tags
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"jobPostings"' in text or '"results"' in text:
                try:
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    data = json.loads(text[start:end])
                    jobs = data.get("jobPostings", data.get("results", []))
                    if jobs:
                        return self._parse_ashby_jobs(jobs)
                except (ValueError, KeyError):
                    pass

        # Parse links from HTML as fallback
        jobs = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if not text or len(text) < 5:
                continue
            if "ashby" in href or "job" in href.lower():
                url = href if href.startswith("http") else f"https://jobs.ashbyhq.com{href}"
                jobs.append(RawJob(
                    company="Sarvam AI",
                    title=text,
                    location="India",
                    url=url,
                    ats_type="custom",
                ))
        logger.info("[Custom/Sarvam] Embed page parse got %d jobs", len(jobs))
        return jobs

    def _playwright_fallback(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[Custom/Sarvam] Playwright not installed")
            return []
        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 AI-JobHunter/1.0")
            try:
                page.goto(self.EMBED_URL, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(3000)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                jobs = self._scrape_embed_page.__func__(self)
            except Exception as exc:
                logger.error("[Custom/Sarvam] Playwright error: %s", exc)
            finally:
                browser.close()
        return jobs

    @staticmethod
    def _strip_html(html: str) -> str:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()
