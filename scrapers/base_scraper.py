"""
base_scraper.py
Defines the RawJob dataclass and the abstract BaseScraper interface.
Every scraper (Greenhouse, Lever, Ashby, custom, aggregator) must implement fetch()
and return a list[RawJob].  Nothing downstream cares about the source.

v3 changes:
  - Added `source` field to RawJob — defaults to company name for ATS scrapers,
    overridden by aggregator scrapers (e.g. "Naukri", "Instahyre", "Wellfound")
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawJob:
    """
    Canonical raw job shape returned by every scraper.
    Fields are intentionally loose — normalizer.py tightens them.
    """
    company: str
    title: str
    location: str
    url: str
    posted_date: Optional[str] = None          # ISO-8601 string or None
    department: Optional[str] = None
    description_snippet: Optional[str] = None  # first ~500 chars of job body
    ats_type: str = "unknown"                  # greenhouse | lever | ashby | custom | aggregator
    source: str = ""                           # v3: which site/platform the job came from
    raw_data: dict = field(default_factory=dict)  # full API response for debugging

    def __post_init__(self):
        # Normalise whitespace in key fields
        self.title = (self.title or "").strip()
        self.location = (self.location or "").strip()
        self.company = (self.company or "").strip()
        self.url = (self.url or "").strip()
        # Default source to "Company careers page" if not set by aggregator
        if not self.source:
            self.source = "Company careers page"


class BaseScraper(abc.ABC):
    """
    Abstract base for all scrapers.

    Subclasses must implement fetch().
    They may optionally override name / ats_type for logging.
    """

    def __init__(self, company_name: str, identifier: str):
        """
        Args:
            company_name: Human-readable company name (e.g. "Postman")
            identifier:   ATS slug or full URL, depending on scraper type
        """
        self.company_name = company_name
        self.identifier = identifier

    @property
    def name(self) -> str:
        return self.company_name

    @abc.abstractmethod
    def fetch(self) -> list[RawJob]:
        """
        Fetch all current job listings and return them as RawJob objects.
        Must not raise — catch internal errors and return an empty list,
        logging the failure so the pipeline continues with other companies.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(company={self.company_name!r}, id={self.identifier!r})"
