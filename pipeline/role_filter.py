"""
pipeline/role_filter.py
First-pass keyword whitelist filter for relevant tech roles.

v3 changes:
  - Broadened from Data Science / AI-ML only to ALSO include Software Development:
    software engineer, SDE, backend, frontend, full-stack, mobile, devops, cloud, platform

Keyword whitelist (case-insensitive substring match on job title):
  data scientist, data science, machine learning, ml engineer, mle,
  ai engineer, applied scientist, genai, gen-ai, llm, nlp,
  data analyst, analytics engineer, mlops, ai research, ai intern, ml intern,
  software engineer, software developer, sde, sde 1, sde 2, sde-1, sde-2,
  backend engineer, backend developer, frontend engineer, frontend developer,
  full stack, fullstack, full-stack, mobile developer, android developer,
  ios developer, devops engineer, cloud engineer, platform engineer
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Whitelist keywords (checked against job TITLE) ────────────────────────────
ROLE_KEYWORDS = [
    # ── Data Science / AI-ML (original + v9 additions) ───────────────────────
    r"\bdata scien",          # "data scientist", "data science"
    r"\bmachine learning\b",
    r"\bml engineer\b",
    r"\b(?:mle)\b",
    r"\bai engineer\b",
    r"\bapplied scientist\b",
    r"\bgenai\b",
    r"\bgen[\s-]ai\b",
    r"\bllm\b",
    r"\bnlp\b",
    r"\bdata anal",           # "data analyst", "data analytics"
    r"\bdata eng\w*",          # "data engineer", "data engineering"
    r"\banalytics engineer\b",
    r"\bmlops\b",
    r"\bai research\b",
    r"\bai intern\b",
    r"\bml intern\b",
    r"\bdeep learning\b",
    r"\bcomputer vision\b",
    r"\bspeech\b.*\bengineer\b",
    r"\bnatural language\b",
    r"\brecommendation\b",
    r"\bai platform\b",
    # ── v9 DS/AI-ML additions ────────────────────────────────────────────────
    r"\bresearch engineer\b",
    r"\bcv engineer\b",        # computer vision engineer (short form)
    r"\bnlp engineer\b",
    r"\bprompt engineer\b",
    r"\bllm engineer\b",
    r"\bai research intern\b",
    r"\bresearch intern\b",
    r"\bquantitative analyst\b",
    r"\bquant researcher\b",
    r"\bdata science intern\b",
    r"\bml research\b",
    r"\bapplied ai\b",
    r"\bgenerative ai\b",
    r"\bdata platform engineer\b",

    # ── Software Development (v3 + v9 additions) ────────────────────────────
    r"\bsoftware engineer\b",
    r"\bsoftware developer\b",
    r"\bsoftware development engineer\b",  # v9
    r"\bsde\b",               # matches SDE, SDE-1, SDE-2, SDE 1, SDE 2
    r"\bsde[\s-]?[12]\b",     # explicit SDE-1, SDE-2, SDE 1, SDE 2
    r"\bsde intern\b",        # v9
    r"\bbackend engineer\b",
    r"\bbackend developer\b",
    r"\bback[\s-]?end\b",     # catch "back end engineer", "back-end developer"
    r"\bfrontend engineer\b",
    r"\bfrontend developer\b",
    r"\bfront[\s-]?end\b",    # catch "front end engineer", "front-end developer"
    r"\bfull[\s-]?stack\b",   # "full stack", "fullstack", "full-stack"
    r"\bmobile developer\b",
    r"\bandroid developer\b",
    r"\bios developer\b",
    r"\bdevops\b",
    r"\bcloud engineer\b",
    r"\bplatform engineer\b",
    r"\bsite reliability\b",  # SRE roles
    # ── v9 SDE additions ─────────────────────────────────────────────────────
    r"\bprogrammer analyst\b",
    r"\bpython developer\b",
    r"\bjava developer\b",
    r"\breact developer\b",
    r"\bnode developer\b",
    r"\bgolang developer\b",
    r"\b(?:sre)\b",            # explicit SRE abbreviation
    r"\bqa engineer\b",
    r"\b(?:sdet)\b",
    r"\bsystems engineer\b",
    r"\binfrastructure engineer\b",
]

_COMPILED = [re.compile(p, re.I) for p in ROLE_KEYWORDS]


def matches_role_whitelist(title: str) -> bool:
    """Return True if the title contains at least one whitelisted keyword."""
    return any(r.search(title) for r in _COMPILED)


def filter_jobs(jobs: list[dict]) -> list[dict]:
    """
    Keep only jobs whose title matches the keyword whitelist.
    Returns the filtered list and logs how many were dropped.
    """
    kept = [j for j in jobs if matches_role_whitelist(j.get("title", ""))]
    dropped = len(jobs) - len(kept)
    logger.debug("role_filter: kept %d / %d  (dropped %d)", len(kept), len(jobs), dropped)
    return kept
