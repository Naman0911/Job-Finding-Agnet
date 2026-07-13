"""
scrapers/naukri.py
Scrapes job listings from Naukri.com via their search API.

Naukri.com is one of India's largest job portals. This scraper uses their
search page structure to query by keywords + location and extract job listings.

v3: New aggregator source added in Change 2.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

NAUKRI_SEARCH_API = "https://www.naukri.com/jobapi/v3/search"


class NaukriScraper(BaseScraper):
    """
    Naukri.com aggregator scraper.

    Instead of a company slug, this scraper takes search keywords and location.
    It queries Naukri's internal API for matching jobs.

    Config entry example:
        {
            "name": "Naukri - AI/ML Jobs Pune",
            "ats_type": "naukri",
            "identifier": "data scientist,machine learning,software engineer",
            "location_priority": "pune",
            "search_location": "pune",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Naukri",
        identifier: str = "",
        search_location: str = "pune",
        request_delay: float = 2.0,
        max_pages: int = 5,
    ):
        super().__init__(company_name, identifier)
        self.keywords = identifier  # comma-separated search terms
        self.search_location = search_location
        self.request_delay = request_delay
        self.max_pages = max_pages

    def fetch(self) -> list[RawJob]:
        """Fetch jobs from Naukri.com search results."""
        logger.info("[Naukri] Searching for '%s' in '%s'", self.keywords, self.search_location)

        all_results: list[RawJob] = []

        # Split keywords and search for each
        keyword_list = [k.strip() for k in self.keywords.split(",") if k.strip()]

        for keyword in keyword_list:
            page_results = self._search_keyword(keyword)
            all_results.extend(page_results)
            time.sleep(self.request_delay)

        # Deduplicate by URL within this scraper run
        seen_urls = set()
        unique_results = []
        for job in all_results:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_results.append(job)

        logger.info("[Naukri] Total unique jobs found: %d", len(unique_results))
        return unique_results

    def _search_keyword(self, keyword: str) -> list[RawJob]:
        """Search Naukri for a single keyword, with pagination."""
        results: list[RawJob] = []

        for page in range(1, self.max_pages + 1):
            try:
                # Naukri's internal search API
                params = {
                    "noOfResults": 50,
                    "urlType": "search_by_key_loc",
                    "searchType": "adv",
                    "keyword": keyword,
                    "location": self.search_location,
                    "pageNo": page,
                    "k": keyword,
                    "l": self.search_location,
                    "experience": "",
                    "salary": "",
                    "glbl_qp_src_n_h": "0",
                }

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "appid": "109",
                    "systemid": "Starter",
                    "Referer": "https://www.naukri.com/",
                }

                resp = requests.get(
                    NAUKRI_SEARCH_API,
                    params=params,
                    headers=headers,
                    timeout=30,
                )

                if resp.status_code == 403:
                    logger.warning("[Naukri] Access blocked (403) — may need to retry later")
                    break

                if resp.status_code != 200:
                    logger.warning("[Naukri] HTTP %d for keyword=%r page=%d", resp.status_code, keyword, page)
                    break

                data = resp.json()
                job_details = data.get("jobDetails", [])

                if not job_details:
                    logger.debug("[Naukri] No more results for %r at page %d", keyword, page)
                    break

                for job in job_details:
                    raw_job = self._parse_job(job)
                    if raw_job:
                        results.append(raw_job)

                logger.info("[Naukri] keyword=%r page=%d → %d jobs", keyword, page, len(job_details))

                # Check if there are more pages
                total_count = data.get("noOfJobs", 0)
                if page * 50 >= total_count:
                    break

                time.sleep(self.request_delay)

            except requests.RequestException as exc:
                logger.error("[Naukri] Request failed for keyword=%r page=%d: %s", keyword, page, exc)
                break
            except (ValueError, KeyError) as exc:
                logger.error("[Naukri] Parse error for keyword=%r page=%d: %s", keyword, page, exc)
                break

        return results

    def _parse_job(self, job: dict) -> Optional[RawJob]:
        """Parse a single Naukri job API response into a RawJob."""
        try:
            title = job.get("title", "").strip()
            company = job.get("companyName", "").strip()
            location_parts = job.get("placeholders", [])
            location = ""
            for ph in location_parts:
                if ph.get("type") == "location":
                    location = ph.get("label", "")
                    break
            if not location:
                location = job.get("jdURL", "").split("/")[-1] if job.get("jdURL") else ""

            url = job.get("jdURL", "")
            if url and not url.startswith("http"):
                url = f"https://www.naukri.com{url}"

            snippet = job.get("jobDescription", "")
            if snippet:
                # Strip HTML
                snippet = re.sub(r"<[^>]+>", " ", snippet)
                snippet = re.sub(r"\s+", " ", snippet).strip()[:500]

            posted_date = job.get("createdDate", "") or job.get("footerPlaceholderLabel", "")

            return RawJob(
                company=company or "Unknown",
                title=title,
                location=location,
                url=url,
                posted_date=str(posted_date) if posted_date else None,
                department=job.get("tagsAndSkills", ""),
                description_snippet=snippet,
                ats_type="aggregator",
                source="Naukri",
                raw_data=job,
            )
        except Exception as exc:
            logger.warning("[Naukri] Failed to parse job: %s", exc)
            return None
