"""
milestone1_test.py
Milestone 1 validation script — fetches Postman jobs from Greenhouse and prints them.
Run this to verify the scraper works before wiring up the full pipeline.

Usage:
    python milestone1_test.py
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output on Windows to handle emoji
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.greenhouse import GreenhouseScraper

if __name__ == "__main__":
    print("=" * 60)
    print("Milestone 1: Greenhouse Scraper — Postman")
    print("=" * 60)

    scraper = GreenhouseScraper("Postman", "postman")
    jobs = scraper.fetch()

    if not jobs:
        print("❌ No jobs returned — check your internet connection")
        sys.exit(1)

    print(f"✅ {len(jobs)} total jobs from Postman's Greenhouse board\n")
    print("All jobs:")
    print("-" * 60)
    for i, job in enumerate(jobs, 1):
        print(f"{i:3}. {job.title}")
        print(f"     Location: {job.location}")
        print(f"     URL: {job.url}")
        print()

    print("=" * 60)
    print("Milestone 1 DONE ✅")
    print("=" * 60)
