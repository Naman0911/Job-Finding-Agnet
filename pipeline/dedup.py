"""
pipeline/dedup.py
Hash-based deduplication layer.

Uses the `dedup_hash` field (sha256 of company+title+location+url)
already computed by normalizer.py.  Queries the database to determine
which jobs are truly new.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.db import JobDatabase

logger = logging.getLogger(__name__)


def filter_new_jobs(jobs: list[dict], db: "JobDatabase") -> list[dict]:
    """
    Return only jobs whose dedup_hash is NOT already in the seen_hashes set
    (loaded from the database).

    Args:
        jobs: List of normalised job dicts (must have 'dedup_hash' key).
        db:   An open JobDatabase instance.

    Returns:
        List of new (unseen) jobs.
    """
    if not jobs:
        return []

    seen_hashes = db.get_seen_hashes()
    new_jobs = [j for j in jobs if j["dedup_hash"] not in seen_hashes]

    logger.info(
        "[dedup] %d total → %d new  (%d already seen)",
        len(jobs), len(new_jobs), len(jobs) - len(new_jobs),
    )
    return new_jobs
