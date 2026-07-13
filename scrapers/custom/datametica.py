"""
scrapers/custom/datametica.py
Scraper for Datametica Solutions (Pune) — now rebranded as Onix.
Datametica.com redirects to onixnet.com which uses Darwinbox ATS.
Darwinbox API endpoint: https://onixnet.darwinbox.in/ms/candidatev2/main/careers/allJobs
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class DatameticaScraper(BaseScraper):
    """
    Scraper for Datametica/Onix careers via Darwinbox ATS.
    Note: Datametica was acquired by Onix. Careers are now at onixnet.darwinbox.in.
    """

    # Darwinbox API — returns JSON with job listings
    DARWIN_API = "https://onixnet.darwinbox.in/ms/candidatev2/main/careers/allJobs"
    DARWIN_JOBS_API = "https://onixnet.darwinbox.in/ms/candidate/api/careers/getAllActiveJobPostings"
    PORTAL_URL = "https://onixnet.darwinbox.in/ms/candidate/careers"

    def __init__(self):
        super().__init__("Datametica", self.PORTAL_URL)

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Datametica] Starting fetch via Darwinbox/Onix")

        # Try Darwinbox REST API first
        jobs = self._fetch_darwinbox_api()
        if jobs:
            return jobs

        # Fall back to Playwright-rendered page
        logger.info("[Custom/Datametica] API returned nothing — trying Playwright")
        return self._fetch_via_playwright()

    def _fetch_darwinbox_api(self) -> list[RawJob]:
        """Try the Darwinbox job postings API."""
        for api_url in [self.DARWIN_JOBS_API, self.DARWIN_API]:
            try:
                resp = requests.get(
                    api_url,
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0 AI-JobHunter/1.0",
                        "Accept": "application/json, text/html",
                        "Referer": "https://onixnet.darwinbox.in/ms/candidate/careers",
                    },
                )
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                    jobs = self._parse_darwinbox_json(data)
                    if jobs:
                        logger.info("[Custom/Datametica] Got %d jobs from Darwinbox API", len(jobs))
                        return jobs
                except ValueError:
                    pass
            except requests.RequestException as exc:
                logger.debug("[Custom/Datametica] API %s failed: %s", api_url, exc)

        return []

    def _parse_darwinbox_json(self, data: dict | list) -> list[RawJob]:
        """Parse Darwinbox JSON response."""
        jobs_raw = []
        if isinstance(data, list):
            jobs_raw = data
        elif isinstance(data, dict):
            for key in ("data", "jobs", "jobPostings", "results", "items"):
                if key in data:
                    jobs_raw = data[key]
                    break

        results = []
        for job in jobs_raw:
            if not isinstance(job, dict):
                continue
            title = job.get("position_name") or job.get("job_title") or job.get("title", "")
            location = (job.get("location_name") or job.get("location") or
                        job.get("city") or "Pune, India")
            job_id = job.get("job_id") or job.get("id") or ""
            url = (f"https://onixnet.darwinbox.in/ms/candidatev2/main/careers/jobDetails/{job_id}"
                   if job_id else self.PORTAL_URL)
            if not title:
                continue
            results.append(RawJob(
                company="Datametica",
                title=title,
                location=location,
                url=url,
                ats_type="custom",
                raw_data=job,
            ))
        return results

    def _fetch_via_playwright(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[Custom/Datametica] Playwright not installed")
            return []

        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 AI-JobHunter/1.0")
            try:
                page.goto(self.PORTAL_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

                # Try to click "Open Jobs" if visible
                try:
                    page.get_by_text("Open Jobs", exact=False).first.click()
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Intercept network calls for job data
                html = page.content()
                with open("diagnostics/onix_careers_loaded.html", "w", encoding="utf-8") as f:
                    f.write(html)
                soup = BeautifulSoup(html, "html.parser")
                jobs = self._parse_playwright_html(soup)
            except Exception as exc:
                logger.error("[Custom/Datametica] Playwright error: %s", exc)
            finally:
                browser.close()

        logger.info("[Custom/Datametica] Playwright found %d jobs", len(jobs))
        return jobs

    def _parse_playwright_html(self, soup: BeautifulSoup) -> list[RawJob]:
        """Parse Darwinbox job board HTML after JS rendering."""
        jobs = []

        # Darwinbox job listings are inside div tags with class 'jobs-section' and an ID
        cards = soup.find_all("div", class_="jobs-section")
        logger.info("[Custom/Datametica] Found %d jobs-section elements in HTML", len(cards))

        for card in cards:
            job_id = card.get("id")
            if not job_id:
                continue

            # Find title
            title_el = card.find("span", class_="job-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            # Find location
            location = "Pune, India"
            loc_sub = card.find("div", class_="sub-section")
            # If the first sub-section has location icon
            if loc_sub and loc_sub.find("img", src=re.compile(r"location", re.I)):
                loc_span = loc_sub.find("span")
                if loc_span:
                    location = loc_span.get_text(strip=True)

            url = f"https://onixnet.darwinbox.in/ms/candidatev2/main/careers/jobDetails/{job_id}"

            jobs.append(RawJob(
                company="Datametica",
                title=title,
                location=location,
                url=url,
                ats_type="custom",
            ))

        return jobs

