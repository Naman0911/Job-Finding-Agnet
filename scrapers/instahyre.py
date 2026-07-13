"""
scrapers/instahyre.py
Scrapes job listings from Instahyre — an India-focused startup job board.

Instahyre is a curated job platform popular among Indian startups for
AI/ML, engineering, and product roles. This scraper queries their
public job listing pages.

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

INSTAHYRE_SEARCH_URL = "https://www.instahyre.com/search-jobs/"


class InstahyreScraper(BaseScraper):
    """
    Instahyre aggregator scraper.

    Searches Instahyre job listings by keyword and location.
    Uses the public-facing search page since Instahyre doesn't expose a public API.

    Config entry example:
        {
            "name": "Instahyre - Tech Jobs Pune",
            "ats_type": "instahyre",
            "identifier": "data scientist,software engineer",
            "search_location": "pune",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Instahyre",
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
        """Fetch jobs from Instahyre search."""
        logger.info("[Instahyre] Searching for '%s' in '%s'", self.keywords, self.search_location)

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

        logger.info("[Instahyre] Total unique jobs found: %d", len(unique))
        return unique

    def _search_keyword(self, keyword: str) -> list[RawJob]:
        """Search Instahyre for a single keyword with pagination."""
        results: list[RawJob] = []

        for page in range(1, self.max_pages + 1):
            try:
                # Instahyre uses query parameters for search
                params = {
                    "job_title": keyword,
                    "location": self.search_location,
                    "page": page,
                }

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }

                resp = requests.get(
                    INSTAHYRE_SEARCH_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )

                if resp.status_code != 200:
                    logger.warning("[Instahyre] HTTP %d for keyword=%r page=%d", resp.status_code, keyword, page)
                    break

                soup = BeautifulSoup(resp.text, "lxml")

                # Look for job cards in the page
                job_cards = soup.select("div.job-card, div.opportunity-card, article.job")
                if not job_cards:
                    # Try alternative selectors
                    job_cards = soup.find_all("div", class_=re.compile(r"job|opportunity|listing", re.I))

                if not job_cards:
                    logger.debug("[Instahyre] No job cards found for %r page %d", keyword, page)
                    break

                for card in job_cards:
                    raw_job = self._parse_card(card)
                    if raw_job:
                        results.append(raw_job)

                logger.info("[Instahyre] keyword=%r page=%d → %d jobs", keyword, page, len(job_cards))
                time.sleep(self.request_delay)

            except requests.RequestException as exc:
                logger.error("[Instahyre] Request failed for keyword=%r: %s", keyword, exc)
                break
            except Exception as exc:
                logger.error("[Instahyre] Parse error: %s", exc)
                break

        return results

    def _parse_card(self, card) -> Optional[RawJob]:
        """Parse a single job card from Instahyre HTML."""
        try:
            # Extract title
            title_el = card.find("h2") or card.find("h3") or card.find("a", class_=re.compile(r"title", re.I))
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract company
            company_el = card.find("span", class_=re.compile(r"company", re.I)) or card.find("h4")
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
                    url = f"https://www.instahyre.com{url}"

            # Extract snippet
            desc_el = card.find("p") or card.find("div", class_=re.compile(r"desc", re.I))
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
                source="Instahyre",
            )
        except Exception as exc:
            logger.warning("[Instahyre] Failed to parse card: %s", exc)
            return None
