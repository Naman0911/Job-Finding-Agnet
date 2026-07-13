"""
scrapers/glassdoor.py
Scrapes job listings from Glassdoor via their public search pages.

Glassdoor does not offer a free public API for job search. This scraper
queries Glassdoor's public job search and extracts listings using
BeautifulSoup.

v9: New aggregator source added in Change 18.

WARNING: Glassdoor uses aggressive bot protection and may block requests.
This scraper is inherently fragile and may need periodic maintenance.
It fails gracefully (returns empty list) to avoid crashing the pipeline.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

GLASSDOOR_BASE_URL = "https://www.glassdoor.co.in"
GLASSDOOR_JOBS_URL = f"{GLASSDOOR_BASE_URL}/Job"

# Default headers to mimic a real browser
GLASSDOOR_HEADERS = {
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


class GlassdoorScraper(BaseScraper):
    """
    Glassdoor aggregator scraper.

    Config entry example:
        {
            "name": "Glassdoor - Tech Jobs Pune",
            "ats_type": "glassdoor",
            "identifier": "data scientist,software engineer",
            "location_priority": "pune",
            "search_location": "pune",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Glassdoor",
        identifier: str = "",
        search_location: str = "pune",
        request_delay: float = 3.0,
        max_pages: int = 3,
    ):
        super().__init__(company_name, identifier)
        self.keywords = identifier
        self.search_location = search_location
        self.request_delay = request_delay
        self.max_pages = max_pages

    def fetch(self) -> list[RawJob]:
        """Fetch jobs from Glassdoor search results."""
        logger.info(
            "[Glassdoor] Searching for '%s' in '%s'",
            self.keywords, self.search_location,
        )

        all_results: list[RawJob] = []
        keyword_list = [k.strip() for k in self.keywords.split(",") if k.strip()]

        for keyword in keyword_list:
            try:
                page_results = self._search_keyword(keyword)
                all_results.extend(page_results)
            except Exception as exc:
                logger.error(
                    "[Glassdoor] Failed searching keyword '%s': %s",
                    keyword, exc,
                )
            time.sleep(self.request_delay)

        # Deduplicate by URL within this scraper run
        seen_urls = set()
        unique_results = []
        for job in all_results:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_results.append(job)

        logger.info("[Glassdoor] Total unique jobs found: %d", len(unique_results))
        return unique_results

    def _search_keyword(self, keyword: str) -> list[RawJob]:
        """Search Glassdoor for a single keyword, with pagination."""
        results: list[RawJob] = []

        for page in range(1, self.max_pages + 1):
            try:
                # Glassdoor search URL pattern
                # Example: /Job/pune-data-scientist-jobs-SRCH_IL.0,4_IC2856202_KO5,19.htm
                search_term = keyword.replace(" ", "-").lower()
                location_term = self.search_location.replace(" ", "-").lower()

                # Build the search URL
                url = (
                    f"{GLASSDOOR_JOBS_URL}/{location_term}-{search_term}-jobs"
                    f"-SRCH_KO0,{len(search_term)}"
                )
                if page > 1:
                    url += f"_IP{page}"
                url += ".htm"

                resp = requests.get(
                    url,
                    headers=GLASSDOOR_HEADERS,
                    timeout=30,
                )

                if resp.status_code == 403:
                    logger.warning(
                        "[Glassdoor] Access blocked (403) — "
                        "bot protection likely active. Skipping."
                    )
                    break

                if resp.status_code != 200:
                    logger.warning(
                        "[Glassdoor] HTTP %d for keyword=%r page=%d",
                        resp.status_code, keyword, page,
                    )
                    break

                soup = BeautifulSoup(resp.text, "lxml")

                # Glassdoor uses structured data (JSON-LD) which is more reliable
                job_cards = self._extract_from_html(soup)

                if not job_cards:
                    logger.debug(
                        "[Glassdoor] No more results for %r at page %d",
                        keyword, page,
                    )
                    break

                results.extend(job_cards)
                logger.info(
                    "[Glassdoor] keyword=%r page=%d → %d jobs",
                    keyword, page, len(job_cards),
                )
                time.sleep(self.request_delay)

            except requests.RequestException as exc:
                logger.error(
                    "[Glassdoor] Request failed for keyword=%r page=%d: %s",
                    keyword, page, exc,
                )
                break
            except Exception as exc:
                logger.error(
                    "[Glassdoor] Parse error for keyword=%r page=%d: %s",
                    keyword, page, exc,
                )
                break

        return results

    def _extract_from_html(self, soup: BeautifulSoup) -> list[RawJob]:
        """Extract job listings from Glassdoor HTML."""
        jobs: list[RawJob] = []

        # Try JSON-LD structured data first (most reliable)
        import json
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "JobPosting":
                            job = self._parse_jsonld(item)
                            if job:
                                jobs.append(job)
                elif isinstance(data, dict):
                    if data.get("@type") == "JobPosting":
                        job = self._parse_jsonld(data)
                        if job:
                            jobs.append(job)
                    elif data.get("@type") == "ItemList":
                        for elem in data.get("itemListElement", []):
                            item = elem.get("item", elem)
                            if item.get("@type") == "JobPosting":
                                job = self._parse_jsonld(item)
                                if job:
                                    jobs.append(job)
            except (json.JSONDecodeError, AttributeError):
                continue

        if jobs:
            return jobs

        # Fallback: parse HTML job cards
        card_selectors = [
            "li.JobsList_jobListItem__wjTHv",
            "li[data-test='jobListing']",
            "div.jobCard",
            "article.job-listing",
        ]

        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                for card in cards:
                    job = self._parse_html_card(card)
                    if job:
                        jobs.append(job)
                break

        return jobs

    def _parse_jsonld(self, data: dict) -> Optional[RawJob]:
        """Parse a JSON-LD JobPosting into a RawJob."""
        try:
            title = data.get("title", "").strip()
            if not title:
                return None

            # Extract company
            org = data.get("hiringOrganization", {})
            if isinstance(org, dict):
                company = org.get("name", "").strip()
            else:
                company = str(org).strip()

            # Extract location
            loc = data.get("jobLocation", {})
            location = ""
            if isinstance(loc, dict):
                address = loc.get("address", {})
                if isinstance(address, dict):
                    parts = [
                        address.get("addressLocality", ""),
                        address.get("addressRegion", ""),
                    ]
                    location = ", ".join(p for p in parts if p)
            elif isinstance(loc, list) and loc:
                first_loc = loc[0]
                if isinstance(first_loc, dict):
                    address = first_loc.get("address", {})
                    if isinstance(address, dict):
                        parts = [
                            address.get("addressLocality", ""),
                            address.get("addressRegion", ""),
                        ]
                        location = ", ".join(p for p in parts if p)

            # Extract URL
            url = data.get("url", "")
            if url and not url.startswith("http"):
                url = f"{GLASSDOOR_BASE_URL}{url}"

            # Extract snippet from description
            description = data.get("description", "")
            if description:
                # Strip HTML tags
                snippet = re.sub(r"<[^>]+>", " ", description)
                snippet = re.sub(r"\s+", " ", snippet).strip()[:500]
            else:
                snippet = ""

            # Extract posted date
            posted_date = data.get("datePosted", "")

            return RawJob(
                company=company or "Unknown",
                title=title,
                location=location,
                url=url,
                posted_date=posted_date if posted_date else None,
                department="",
                description_snippet=snippet,
                ats_type="aggregator",
                source="Glassdoor",
            )
        except Exception as exc:
            logger.warning("[Glassdoor] Failed to parse JSON-LD job: %s", exc)
            return None

    def _parse_html_card(self, card) -> Optional[RawJob]:
        """Parse a single Glassdoor HTML job card into a RawJob."""
        try:
            # Extract title
            title_el = card.select_one("a.jobTitle") or card.select_one("a[data-test='job-link']")
            if not title_el:
                title_el = card.select_one("a")
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract company
            company_el = card.select_one("div.EmployerProfile_compactEmployerName__LE242")
            if not company_el:
                company_el = card.select_one("span.EmployerProfile_employerName__Xemli")
            if not company_el:
                company_el = card.select_one(".job-search-company")
            company = company_el.get_text(strip=True) if company_el else ""

            # Extract location
            location_el = card.select_one("div[data-test='emp-location']")
            if not location_el:
                location_el = card.select_one(".location")
            location = location_el.get_text(strip=True) if location_el else ""

            # Extract URL
            url = ""
            if title_el and title_el.name == "a":
                href = title_el.get("href", "")
                if href:
                    if not href.startswith("http"):
                        url = f"{GLASSDOOR_BASE_URL}{href}"
                    else:
                        url = href

            if not title:
                return None

            return RawJob(
                company=company or "Unknown",
                title=title,
                location=location,
                url=url,
                posted_date=None,
                department="",
                description_snippet="",
                ats_type="aggregator",
                source="Glassdoor",
            )
        except Exception as exc:
            logger.warning("[Glassdoor] Failed to parse HTML card: %s", exc)
            return None
