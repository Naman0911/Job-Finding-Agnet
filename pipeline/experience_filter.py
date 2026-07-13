"""
pipeline/experience_filter.py
Second-pass keyword filter focusing on experience requirements.

v4 addition: Filters for entry-level/fresher roles and explicitly rejects senior roles.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Keywords that indicate a role is too senior
SENIOR_KEYWORDS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b", r"\bstaff\b",
    r"\bmanager\b", r"\bdirector\b", r"\bhead of\b",
    r"5\+\s*years?", r"4\+\s*years?", r"3\+\s*years?", r"2\+\s*years?\s*experience",
    r"minimum 2 years?", r"minimum 3 years?", r"experienced professional"
]

# Keywords that indicate a role is entry-level/fresher friendly
FRESHER_KEYWORDS = [
    r"\bfreshers?\b", r"\bentry[- ]?level\b", r"\bgraduate(?: trainee)?\b",
    r"\bcampus hire\b", r"\bassociate\b", r"\bjunior\b", r"\bjr\.?\b",
    r"\bintern(?:ship)?\b", r"\btrainee\b",
    r"0-1\s*years?", r"0-2\s*years?", r"early career\b", r"new grad\b",
    r"recent graduate\b"
]

_SENIOR_COMPILED = [re.compile(p, re.I) for p in SENIOR_KEYWORDS]
_FRESHER_COMPILED = [re.compile(p, re.I) for p in FRESHER_KEYWORDS]

def is_senior_role(text: str) -> bool:
    return any(r.search(text) for r in _SENIOR_COMPILED)

def is_fresher_role(text: str) -> bool:
    return any(r.search(text) for r in _FRESHER_COMPILED)

from typing import Tuple

def classify(job: dict) -> Tuple[bool, bool, bool]:
    """
    Evaluates a job based on experience requirements.
    Returns: (is_auto_accepted, is_auto_rejected, is_ambiguous)
    """
    title = job.get("title", "")
    snippet = job.get("description_snippet", "")
    full_text = f"{title} {snippet}"
    
    # If it matches fresher keywords, keep it
    if is_fresher_role(full_text):
        return True, False, False  # Auto-accept
        
    # If it matches senior keywords and didn't match fresher, drop it
    if is_senior_role(full_text):
        return False, True, False  # Auto-reject
        
    # If no experience requirement mentioned at all (matches neither), it's ambiguous
    return False, False, True  # Ambiguous

