"""
pipeline/normalizer.py
Converts a RawJob into a fully validated, normalised Job dict
that is safe to store in SQLite and send to notifiers.

v3 changes:
  - Added `source` field to normalised output (from RawJob.source)
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from scrapers.base_scraper import RawJob


def normalise(raw: RawJob) -> dict:
    """
    Normalise a RawJob into a clean dict with guaranteed non-None fields.

    Returns a dict matching the `jobs` table schema:
        company, title, location, url, posted_date,
        first_seen_at, dedup_hash, notified, source
    """
    company = _clean(raw.company) or "Unknown"
    title = _clean(raw.title) or "Unknown"
    location = _clean(raw.location) or ""
    url = _clean(raw.url) or ""

    posted_date = _normalise_date(raw.posted_date)
    first_seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dedup_hash = _make_hash(company, title, location, url)

    return {
        "company": company,
        "title": title,
        "location": location,
        "url": url,
        "posted_date": posted_date,
        "first_seen_at": first_seen_at,
        "dedup_hash": dedup_hash,
        "notified": 0,
        "department": _clean(raw.department) or "",
        "description_snippet": _clean(raw.description_snippet) or "",
        "ats_type": raw.ats_type or "unknown",
        "source": _clean(raw.source) or "Company careers page",
    }


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    # Collapse internal whitespace and strip
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalise_date(raw_date: Optional[str]) -> str:
    """
    Try to parse raw_date (ISO string, epoch ms, or arbitrary) into
    an ISO-8601 UTC date string.  Return empty string on failure.
    """
    if not raw_date:
        return ""
    raw = str(raw_date).strip()

    # Already looks like ISO
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]

    # Epoch milliseconds (13 digits)
    if re.match(r"^\d{13}$", raw):
        try:
            dt = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
            return dt.date().isoformat()
        except (ValueError, OSError):
            pass

    # Epoch seconds (10 digits)
    if re.match(r"^\d{10}$", raw):
        try:
            dt = datetime.fromtimestamp(int(raw), tz=timezone.utc)
            return dt.date().isoformat()
        except (ValueError, OSError):
            pass

    return ""


def _make_hash(company: str, title: str, location: str, url: str) -> str:
    """SHA-256 of the four canonical fields (lowercase, stripped)."""
    key = f"{company.lower()}|{title.lower()}|{location.lower()}|{url.lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
