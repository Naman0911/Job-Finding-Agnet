"""
scrapers/custom/chargebee.py
Custom scraper for Chargebee careers page.
Chargebee uses a custom career page that embeds Greenhouse.
We fetch the page using requests and parse jobs from the embedded JSON or HTML.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)


class ChargebeeScraper(BaseScraper):
    """
    Chargebee careers scraper.
    Their careers page is at chargebee.com/careers/ and embeds Greenhouse.
    We try to fetch their Greenhouse board via a known API URL, then fall back to HTML.
    """

    # Chargebee's Greenhouse embed uses a different board name
    GREENHOUSE_SLUGS = ["chargebee", "chargebee1", "chargebeeinc"]
    CAREERS_URL = "https://www.chargebee.com/careers/"

    def __init__(self):
        super().__init__("Chargebee", self.CAREERS_URL)

    def fetch(self) -> list[RawJob]:
        logger.info("[Custom/Chargebee] Starting fetch")

        # Try Greenhouse slugs first
        for slug in self.GREENHOUSE_SLUGS:
            from scrapers.greenhouse import GreenhouseScraper
            scraper = GreenhouseScraper("Chargebee", slug)
            try:
                jobs = scraper.fetch()
                if jobs:
                    logger.info("[Custom/Chargebee] Got %d jobs from Greenhouse slug=%r", len(jobs), slug)
                    return jobs
            except Exception:
                continue

        # Fall back to parsing the HTML careers page
        logger.info("[Custom/Chargebee] Greenhouse slugs failed — trying HTML parse")
        return self._fetch_html()

    def _fetch_html(self) -> list[RawJob]:
        try:
            resp = requests.get(
                self.CAREERS_URL,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 AI-JobHunter/1.0"},
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[Custom/Chargebee] Request failed: %s", exc)
            return self._playwright_fallback()

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse(soup)

    def _parse(self, soup: BeautifulSoup) -> list[RawJob]:
        jobs = []
        # Look for job-related anchors
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if not text or len(text) < 5 or len(text) > 120:
                continue
            if not re.search(r"job|career|role|position|apply|opening", href + text, re.I):
                continue
            url = href if href.startswith("http") else f"https://www.chargebee.com{href}"
            jobs.append(RawJob(
                company="Chargebee",
                title=text,
                location="India",  # Chargebee is primarily India-headquartered
                url=url,
                ats_type="custom",
            ))
        return jobs

    def _playwright_fallback(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []
        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 AI-JobHunter/1.0")
            try:
                page.goto(self.CAREERS_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)
                html = page.content()
                jobs = self._parse(BeautifulSoup(html, "html.parser"))
            except Exception as exc:
                logger.error("[Custom/Chargebee] Playwright error: %s", exc)
            finally:
                browser.close()
        return jobs
