"""
scrapers/indeed.py
Scrapes job listings from Indeed.com via their public search pages.

Indeed does not offer a free public API for job search. This scraper
queries Indeed's public search results and extracts job listings using
BeautifulSoup.

v9: New aggregator source added in Change 18.

WARNING: Indeed uses Cloudflare bot protection and may block requests.
This scraper is inherently fragile and may need periodic maintenance.
It fails gracefully (returns empty list) to avoid crashing the pipeline.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus, urlencode

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

INDEED_BASE_URL = "https://www.indeed.com"
INDEED_SEARCH_URL = f"{INDEED_BASE_URL}/jobs"

# Default headers to mimic a real browser
INDEED_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class IndeedScraper(BaseScraper):
    """
    Indeed.com aggregator scraper.

    Config entry example:
        {
            "name": "Indeed - AI/ML Jobs Pune",
            "ats_type": "indeed",
            "identifier": "data scientist,machine learning engineer",
            "location_priority": "pune",
            "search_location": "Pune, Maharashtra",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Indeed",
        identifier: str = "",
        search_location: str = "Pune, Maharashtra",
        request_delay: float = 3.0,
        max_pages: int = 3,
    ):
        super().__init__(company_name, identifier)
        self.keywords = identifier
        self.search_location = search_location
        self.request_delay = request_delay
        self.max_pages = max_pages

    def fetch(self) -> list[RawJob]:
        """Fetch jobs from Indeed.com search results."""
        logger.info("[Indeed] Searching for '%s' in '%s'", self.keywords, self.search_location)

        all_results: list[RawJob] = []
        keyword_list = [k.strip() for k in self.keywords.split(",") if k.strip()]

        for keyword in keyword_list:
            try:
                page_results = self._search_keyword(keyword)
                all_results.extend(page_results)
            except Exception as exc:
                logger.error("[Indeed] Failed searching keyword '%s': %s", keyword, exc)
            time.sleep(self.request_delay)

        # Deduplicate by URL within this scraper run
        seen_urls = set()
        unique_results = []
        for job in all_results:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_results.append(job)

        logger.info("[Indeed] Total unique jobs found: %d", len(unique_results))
        return unique_results

    def _search_keyword(self, keyword: str) -> list[RawJob]:
        """Search Indeed for a single keyword, with pagination."""
        results: list[RawJob] = []

        for page in range(self.max_pages):
            try:
                params = {
                    "q": keyword,
                    "l": self.search_location,
                    "start": page * 10,  # Indeed uses 10 results per page
                    "fromage": 7,  # Last 7 days only
                }

                resp = requests.get(
                    INDEED_SEARCH_URL,
                    params=params,
                    headers=INDEED_HEADERS,
                    timeout=30,
                )

                if resp.status_code == 403:
                    logger.warning(
                        "[Indeed] Access blocked (403) for keyword=%r — "
                        "Cloudflare/bot protection likely active. Skipping.",
                    )
                    break

                if resp.status_code != 200:
                    logger.warning(
                        "[Indeed] HTTP %d for keyword=%r page=%d",
                        resp.status_code, keyword, page,
                    )
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                job_cards = soup.select("div.job_seen_beacon") or soup.select("div.jobsearch-ResultsList > div")

                if not job_cards:
                    logger.debug("[Indeed] No more results for %r at page %d", keyword, page)
                    break

                for card in job_cards:
                    raw_job = self._parse_card(card)
                    if raw_job:
                        results.append(raw_job)

                logger.info(
                    "[Indeed] keyword=%r page=%d → %d cards",
                    keyword, page, len(job_cards),
                )
                time.sleep(self.request_delay)

            except requests.RequestException as exc:
                logger.error("[Indeed] Request failed for keyword=%r page=%d: %s", keyword, page, exc)
                break
            except Exception as exc:
                logger.error("[Indeed] Parse error for keyword=%r page=%d: %s", keyword, page, exc)
                break

        return results

    def _parse_card(self, card) -> Optional[RawJob]:
        """Parse a single Indeed job card into a RawJob."""
        try:
            # Extract title
            title_el = card.select_one("h2.jobTitle a") or card.select_one("a[data-jk]")
            if not title_el:
                title_el = card.select_one("h2 a") or card.select_one(".jobTitle span")
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract company
            company_el = card.select_one("span[data-testid='company-name']") or card.select_one("span.companyName")
            if not company_el:
                company_el = card.select_one(".company")
            company = company_el.get_text(strip=True) if company_el else ""

            # Extract location
            location_el = card.select_one("div[data-testid='text-location']") or card.select_one("div.companyLocation")
            if not location_el:
                location_el = card.select_one(".location")
            location = location_el.get_text(strip=True) if location_el else ""

            # Extract URL
            link_el = card.select_one("a[data-jk]") or card.select_one("h2 a")
            url = ""
            if link_el:
                jk = link_el.get("data-jk", "")
                if jk:
                    url = f"{INDEED_BASE_URL}/viewjob?jk={jk}"
                else:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        url = f"{INDEED_BASE_URL}{href}"
                    else:
                        url = href

            # Extract snippet
            snippet_el = card.select_one("div.job-snippet") or card.select_one("table.jobCardShelfContainer")
            snippet = ""
            if snippet_el:
                snippet = snippet_el.get_text(" ", strip=True)[:500]

            if not title:
                return None

            return RawJob(
                company=company or "Unknown",
                title=title,
                location=location,
                url=url,
                posted_date=None,
                department="",
                description_snippet=snippet,
                ats_type="aggregator",
                source="Indeed",
            )
        except Exception as exc:
            logger.warning("[Indeed] Failed to parse job card: %s", exc)
            return None
