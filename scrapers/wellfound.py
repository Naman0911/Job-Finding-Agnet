"""
scrapers/wellfound.py
Scrapes job listings from Wellfound (formerly AngelList Talent).

Wellfound is a startup-focused job board, very popular for India-based
tech startups. This scraper uses their GraphQL API to search for jobs.

v3: New aggregator source added in Change 2.

Note on LinkedIn: Per the plan, we do NOT scrape LinkedIn directly because it
violates their ToS and they actively block scrapers. If a legitimate API path
opens up later, a separate LinkedIn module can be added.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

import requests

from scrapers.base_scraper import BaseScraper, RawJob

logger = logging.getLogger(__name__)

# Wellfound uses a GraphQL API for job searches
WELLFOUND_GRAPHQL_URL = "https://wellfound.com/graphql"
WELLFOUND_SEARCH_URL = "https://wellfound.com/role/r/{role_slug}/l/{location_slug}"


class WellfoundScraper(BaseScraper):
    """
    Wellfound (AngelList) aggregator scraper.

    Queries Wellfound's public-facing job search for startup roles.

    Config entry example:
        {
            "name": "Wellfound - Startup Jobs Pune",
            "ats_type": "wellfound",
            "identifier": "software-engineer,data-scientist",
            "search_location": "pune",
            "enabled": true
        }
    """

    def __init__(
        self,
        company_name: str = "Wellfound",
        identifier: str = "",
        search_location: str = "india",
        request_delay: float = 2.0,
        max_pages: int = 3,
    ):
        super().__init__(company_name, identifier)
        self.role_slugs = identifier  # comma-separated role slugs
        self.search_location = search_location
        self.request_delay = request_delay
        self.max_pages = max_pages

    def fetch(self) -> list[RawJob]:
        """Fetch jobs from Wellfound."""
        logger.info("[Wellfound] Searching for roles '%s' in '%s'", self.role_slugs, self.search_location)

        all_results: list[RawJob] = []
        slug_list = [s.strip() for s in self.role_slugs.split(",") if s.strip()]

        for role_slug in slug_list:
            page_results = self._search_role(role_slug)
            all_results.extend(page_results)
            time.sleep(self.request_delay)

        # Deduplicate by URL
        seen_urls = set()
        unique = []
        for job in all_results:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique.append(job)

        logger.info("[Wellfound] Total unique jobs found: %d", len(unique))
        return unique

    def _search_role(self, role_slug: str) -> list[RawJob]:
        """Search Wellfound for a specific role slug."""
        results: list[RawJob] = []

        for page in range(1, self.max_pages + 1):
            try:
                # Try the GraphQL API first
                gql_results = self._try_graphql(role_slug, page)
                if gql_results is not None:
                    results.extend(gql_results)
                    if len(gql_results) < 10:  # Less than full page = last page
                        break
                    time.sleep(self.request_delay)
                    continue

                # Fallback: scrape the HTML page
                html_results = self._try_html(role_slug, page)
                results.extend(html_results)
                if not html_results:
                    break
                time.sleep(self.request_delay)

            except Exception as exc:
                logger.error("[Wellfound] Error for role=%r page=%d: %s", role_slug, page, exc)
                break

        return results

    def _try_graphql(self, role_slug: str, page: int) -> Optional[list[RawJob]]:
        """Try Wellfound's GraphQL API for job listings."""
        try:
            query = """
            query JobListings($roleSlug: String!, $locationSlug: String!, $page: Int!) {
                jobListings(
                    roleSlug: $roleSlug,
                    locationSlug: $locationSlug,
                    page: $page
                ) {
                    startupJobs {
                        id
                        title
                        slug
                        remoteOk
                        primaryRoleTitle
                        liveStartAt
                        locationNames
                        compensation
                        startup {
                            name
                            companyUrl
                        }
                    }
                }
            }
            """

            payload = {
                "query": query,
                "variables": {
                    "roleSlug": role_slug,
                    "locationSlug": self.search_location,
                    "page": page,
                },
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }

            resp = requests.post(
                WELLFOUND_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if resp.status_code != 200:
                logger.debug("[Wellfound] GraphQL returned %d — falling back to HTML", resp.status_code)
                return None

            data = resp.json()
            jobs_data = (
                data.get("data", {})
                .get("jobListings", {})
                .get("startupJobs", [])
            )

            if not jobs_data:
                return []

            results = []
            for job in jobs_data:
                startup = job.get("startup", {})
                company_name = startup.get("name", "Unknown")
                title = job.get("title", "") or job.get("primaryRoleTitle", "")
                locations = job.get("locationNames", [])
                location = ", ".join(locations) if locations else ""
                slug = job.get("slug", "")
                url = f"https://wellfound.com/jobs/{slug}" if slug else ""

                results.append(RawJob(
                    company=company_name,
                    title=title,
                    location=location,
                    url=url,
                    posted_date=job.get("liveStartAt"),
                    department="",
                    description_snippet=job.get("compensation", ""),
                    ats_type="aggregator",
                    source="Wellfound",
                    raw_data=job,
                ))

            logger.info("[Wellfound] GraphQL role=%r page=%d → %d jobs", role_slug, page, len(results))
            return results

        except Exception as exc:
            logger.debug("[Wellfound] GraphQL failed: %s — falling back to HTML", exc)
            return None

    def _try_html(self, role_slug: str, page: int) -> list[RawJob]:
        """Fallback: scrape Wellfound's HTML job listing page."""
        results: list[RawJob] = []

        try:
            from bs4 import BeautifulSoup

            location_slug = self.search_location.lower().replace(" ", "-")
            url = f"https://wellfound.com/role/r/{role_slug}/l/{location_slug}"
            if page > 1:
                url += f"?page={page}"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html",
            }

            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.warning("[Wellfound] HTML page returned %d for role=%r", resp.status_code, role_slug)
                return []

            soup = BeautifulSoup(resp.text, "lxml")

            # Look for job cards in the page
            job_cards = soup.select("div[class*='JobListing'], div[class*='styles_result']")
            if not job_cards:
                job_cards = soup.find_all("div", class_=re.compile(r"job|listing|card", re.I))

            for card in job_cards:
                # Title
                title_el = card.find("h2") or card.find("a", class_=re.compile(r"title", re.I))
                title = title_el.get_text(strip=True) if title_el else ""

                # Company
                company_el = card.find("h3") or card.find("span", class_=re.compile(r"company", re.I))
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                loc_el = card.find("span", class_=re.compile(r"location", re.I))
                location = loc_el.get_text(strip=True) if loc_el else ""

                # URL
                link_el = card.find("a", href=True)
                job_url = ""
                if link_el:
                    job_url = link_el["href"]
                    if not job_url.startswith("http"):
                        job_url = f"https://wellfound.com{job_url}"

                if title:
                    results.append(RawJob(
                        company=company,
                        title=title,
                        location=location,
                        url=job_url,
                        ats_type="aggregator",
                        source="Wellfound",
                    ))

            logger.info("[Wellfound] HTML role=%r page=%d → %d jobs", role_slug, page, len(results))

        except ImportError:
            logger.error("[Wellfound] BeautifulSoup not available for HTML fallback")
        except Exception as exc:
            logger.error("[Wellfound] HTML scrape error: %s", exc)

        return results
