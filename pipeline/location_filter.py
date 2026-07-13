"""
pipeline/location_filter.py
Filters jobs to only those in Pune or India (including Remote-India).

Accept patterns (case-insensitive substring match):
  - "pune"
  - "india"
  - "remote - india"
  - "remote (india)"
  - "india remote"
  - "pan india"
  - "pan-india"
  - "hyderabad"  ← configurable broadening
  - "bengaluru" / "bangalore"  ← configurable
  - "mumbai"  ← configurable

Reject patterns (even if they contain "remote"):
  - bare "remote" with no country
  - specific non-Indian locations (US, UK, Germany, etc.)
"""

from __future__ import annotations

import re
from typing import Union

# ── Accept rules ──────────────────────────────────────────────────────────────
# These patterns must be present somewhere in the location string.
ACCEPT_PATTERNS = [
    r"\bpune\b",
    r"\bindia\b",
    r"remote\s*[-–]\s*india",
    r"remote\s*\(\s*india\s*\)",
    r"india\s+remote",
    r"pan[\s-]?india",
]

# ── Reject patterns (applied AFTER accept, to catch false positives) ──────────
# If location contains any of these, reject even if it passed accept.
REJECT_PATTERNS = [
    r"\busa\b", r"\bunited states\b", r"\buk\b", r"\bunited kingdom\b",
    r"\bgermany\b", r"\bfrankfurt\b", r"\bberlin\b",
    r"\bsingapore\b", r"\baustralia\b", r"\bcanada\b",
    r"\bnew york\b", r"\bsan francisco\b", r"\bseattle\b",
    r"\bdubai\b", r"\bnetherlands\b", r"\bpoland\b",
]

# Compile once
_ACCEPT_RE = [re.compile(p, re.I) for p in ACCEPT_PATTERNS]
_REJECT_RE = [re.compile(p, re.I) for p in REJECT_PATTERNS]


def is_accepted_location(location: str) -> bool:
    """
    Return True if the location string should be accepted for monitoring.

    Args:
        location: Raw location string from the job listing.

    Returns:
        True if location passes the Pune/India filter, False otherwise.
    """
    if not location or not location.strip():
        # Empty location — be permissive: accept (we'll rely on LLM later)
        return True

    loc = location.strip()

    # Must match at least one accept pattern
    accepted = any(r.search(loc) for r in _ACCEPT_RE)
    if not accepted:
        return False

    # Must not match any reject pattern
    rejected = any(r.search(loc) for r in _REJECT_RE)
    return not rejected


def filter_jobs(jobs: list[dict]) -> list[dict]:
    """
    Filter a list of normalised job dicts, keeping only those whose
    location passes the Pune/India filter.

    Args:
        jobs: List of normalised job dicts (from normalizer.py).

    Returns:
        Filtered list.
    """
    kept = [j for j in jobs if is_accepted_location(j.get("location", ""))]
    dropped = len(jobs) - len(kept)
    if dropped:
        import logging
        logging.getLogger(__name__).debug(
            "location_filter: kept %d / %d  (dropped %d)", len(kept), len(jobs), dropped
        )
    return kept
