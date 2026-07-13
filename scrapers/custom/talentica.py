"""
scrapers/custom/talentica.py
Custom scraper for Talentica Software (Pune HQ).
Talentica uses their own career portal at https://www.talentica.com/careers/
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class TalenicaScraper(BaseScraper):
    """
    Scraper for Talentica Software career page (custom HTML).
    Tries a direct JSON endpoint first; falls back to HTML parsing.
    """

    BASE_URL = "https://www.talentica.com/careers/"
    JOBS_URL = "https://www.talentica.com/careers/openings/"

    def __init__(self):
        super().__init__("Talentica", "https://www.talentica.com/careers/")

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Talentica] Starting fetch")
        return self._fetch_html()

    def _fetch_html(self) -> list[RawJob]:
        try:
            resp = requests.get(
                self.JOBS_URL,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-JobHunter/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[Custom/Talentica] Request failed: %s", exc)
            return self._fetch_via_playwright()

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = self._parse(soup)
        logger.info("[Custom/Talentica] Found %d jobs from HTML", len(jobs))
        return jobs

    def _parse(self, soup: BeautifulSoup) -> list[RawJob]:
        jobs = []
        # Try various common patterns for job listing pages
        for container in soup.find_all(["div", "li", "article"],
                                        class_=re.compile(r"job|opening|career|position", re.I)):
            title_el = (
                container.find(["h2", "h3", "h4", "span", "a"],
                               class_=re.compile(r"title|role|position", re.I))
                or container.find(["h2", "h3", "h4"])
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            link_el = container.find("a", href=True)
            url = self.BASE_URL
            if link_el:
                href = link_el["href"]
                url = href if href.startswith("http") else f"https://www.talentica.com{href}"

            loc_el = container.find(class_=re.compile(r"location|city", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "Pune, India"

            jobs.append(RawJob(
                company="Talentica",
                title=title,
                location=location,
                url=url,
                ats_type="custom",
            ))

        # If the specific pattern above found nothing, do a generic link scan
        if not jobs:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if len(text) < 5 or len(text) > 150:
                    continue
                if not re.search(r"job|career|opening|apply|position", href + text, re.I):
                    continue
                url = href if href.startswith("http") else f"https://www.talentica.com{href}"
                jobs.append(RawJob(
                    company="Talentica",
                    title=text,
                    location="Pune, India",
                    url=url,
                    ats_type="custom",
                ))
        return jobs

    def _fetch_via_playwright(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[Custom/Talentica] Playwright not installed")
            return []

        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 AI-JobHunter/1.0")
            try:
                page.goto(self.JOBS_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                jobs = self._parse(soup)
                logger.info("[Custom/Talentica] Playwright got %d jobs", len(jobs))
            except Exception as exc:
                logger.error("[Custom/Talentica] Playwright error: %s", exc)
            finally:
                browser.close()
        return jobs
