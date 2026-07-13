"""
scrapers/custom/flytbase.py
Custom scraper for FlytBase (Pune-based drone software company).
FlytBase uses a custom career portal at https://flytbase.com/careers/jobs/
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class FlytBaseScraper(BaseScraper):
    """
    FlytBase careers scraper.
    Uses their custom jobs page. Falls back to Playwright if JavaScript rendering is needed.
    """

    CAREERS_URL = "https://flytbase.com/careers/jobs/"
    FALLBACK_URL = "https://flytbase.com/careers/"

    def __init__(self):
        super().__init__("FlytBase", self.CAREERS_URL)

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/FlytBase] Starting fetch")

        for url in [self.CAREERS_URL, self.FALLBACK_URL]:
            jobs = self._fetch_html(url)
            if jobs:
                return jobs

        # Playwright fallback if both URLs returned nothing
        return self._playwright_fallback()

    def _fetch_html(self, url: str) -> list[RawJob]:
        try:
            resp = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 AI-JobHunter/1.0"},
                allow_redirects=True,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            jobs = self._parse(soup, url)
            if jobs:
                logger.info("[Custom/FlytBase] Got %d jobs from %s", len(jobs), url)
            return jobs
        except requests.RequestException as exc:
            logger.warning("[Custom/FlytBase] Request to %s failed: %s", url, exc)
            return []

    def _parse(self, soup: BeautifulSoup, base_url: str) -> list[RawJob]:
        jobs = []
        for container in soup.find_all(["div", "li", "article"],
                                        class_=re.compile(r"job|career|position|role|opening", re.I)):
            title_el = container.find(["h2", "h3", "h4", "strong"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            link_el = container.find("a", href=True)
            url = base_url
            if link_el:
                href = link_el["href"]
                url = href if href.startswith("http") else f"https://flytbase.com{href}"
            loc_el = container.find(class_=re.compile(r"location|city|loc", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "Pune, India"
            jobs.append(RawJob(
                company="FlytBase",
                title=title,
                location=location,
                url=url,
                ats_type="custom",
            ))
        return jobs

    def _playwright_fallback(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[Custom/FlytBase] Playwright not installed")
            return []
        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 AI-JobHunter/1.0")
            try:
                page.goto(self.CAREERS_URL, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)
                html = page.content()
                jobs = self._parse(BeautifulSoup(html, "html.parser"), self.CAREERS_URL)
                logger.info("[Custom/FlytBase] Playwright got %d jobs", len(jobs))
            except Exception as exc:
                logger.error("[Custom/FlytBase] Playwright error: %s", exc)
            finally:
                browser.close()
        return jobs
