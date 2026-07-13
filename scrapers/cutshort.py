"""
scrapers/cutshort.py
Scrapes job listings from Cutshort — an India-focused tech hiring platform.

Cutshort is a curated hiring platform popular for startup roles in India.
This scraper queries their public job search page.

v3: New aggregator source added in Change 2.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

CUTSHORT_SEARCH_URL = "https://cutshort.io/jobs"


class CutshortScraper(BaseScraper):
    """
    Cutshort aggregator scraper.

    Searches Cutshort job listings by keyword and location.

    Config entry example:
        {
            "name": "Cutshort - Tech Jobs Pune",
            "ats_type": "cutshort",
            "identifier": "data scientist,software engineer",
            "search_location": "pune",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Cutshort",
        identifier: str = "",
        search_location: str = "pune",
        request_delay: float = 2.0,
        max_pages: int = 3,
    ):
        super().__init__(company_name, identifier)
        self.keywords = identifier
        self.search_location = search_location
        self.request_delay = request_delay
        self.max_pages = max_pages

    def fetch(self) -> list[RawJob]:
        """Fetch jobs from Cutshort."""
        logger.info("[Cutshort] Searching for '%s' in '%s'", self.keywords, self.search_location)

        all_results: list[RawJob] = []
        keyword_list = [k.strip() for k in self.keywords.split(",") if k.strip()]

        for keyword in keyword_list:
            page_results = self._search_keyword(keyword)
            all_results.extend(page_results)
            time.sleep(self.request_delay)

        # Deduplicate by URL
        seen_urls = set()
        unique = []
        for job in all_results:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique.append(job)

        logger.info("[Cutshort] Total unique jobs found: %d", len(unique))
        return unique

    def _search_keyword(self, keyword: str) -> list[RawJob]:
        """Search Cutshort for a single keyword."""
        results: list[RawJob] = []

        for page in range(1, self.max_pages + 1):
            try:
                # Cutshort uses URL-based filtering
                search_url = f"{CUTSHORT_SEARCH_URL}/{keyword.replace(' ', '-')}-in-{self.search_location}"
                if page > 1:
                    search_url += f"?page={page}"

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }

                resp = requests.get(search_url, headers=headers, timeout=30)

                if resp.status_code != 200:
                    logger.warning("[Cutshort] HTTP %d for keyword=%r page=%d", resp.status_code, keyword, page)
                    break

                soup = BeautifulSoup(resp.text, "lxml")

                # Find job cards
                job_cards = soup.select("div.job-card, div[class*='JobCard'], article[class*='job']")
                if not job_cards:
                    job_cards = soup.find_all("div", class_=re.compile(r"job|listing|card", re.I))

                if not job_cards:
                    logger.debug("[Cutshort] No job cards found for %r page %d", keyword, page)
                    break

                for card in job_cards:
                    raw_job = self._parse_card(card)
                    if raw_job:
                        results.append(raw_job)

                logger.info("[Cutshort] keyword=%r page=%d → %d jobs", keyword, page, len(job_cards))
                time.sleep(self.request_delay)

            except requests.RequestException as exc:
                logger.error("[Cutshort] Request failed for keyword=%r: %s", keyword, exc)
                break
            except Exception as exc:
                logger.error("[Cutshort] Parse error: %s", exc)
                break

        return results

    def _parse_card(self, card) -> Optional[RawJob]:
        """Parse a single job card from Cutshort HTML."""
        try:
            # Extract title
            title_el = (
                card.find("h2")
                or card.find("h3")
                or card.find("a", class_=re.compile(r"title|name", re.I))
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract company
            company_el = (
                card.find("span", class_=re.compile(r"company", re.I))
                or card.find("h4")
                or card.find("div", class_=re.compile(r"company", re.I))
            )
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            # Extract location
            location_el = card.find("span", class_=re.compile(r"location", re.I))
            location = location_el.get_text(strip=True) if location_el else self.search_location

            # Extract URL
            link_el = card.find("a", href=True)
            url = ""
            if link_el:
                url = link_el["href"]
                if not url.startswith("http"):
                    url = f"https://cutshort.io{url}"

            # Extract snippet
            desc_el = card.find("p") or card.find("div", class_=re.compile(r"desc|skill", re.I))
            snippet = desc_el.get_text(strip=True)[:500] if desc_el else ""

            if not title:
                return None

            return RawJob(
                company=company,
                title=title,
                location=location,
                url=url,
                posted_date=None,
                department="",
                description_snippet=snippet,
                ats_type="aggregator",
                source="Cutshort",
            )
        except Exception as exc:
            logger.warning("[Cutshort] Failed to parse card: %s", exc)
            return None
