"""
scripts/discover_startups.py
Location-based startup discovery tool for the AI Job Hunter agent.

v9 Change 18: Semi-automated discovery of new tech companies in Pune/India.

This is a standalone script (NOT part of the 8-hour pipeline) — designed
to be run weekly or on-demand to discover new companies to add to
companies.json.

Discovery flow:
  1. Search Google News RSS for recent articles about Pune/India AI-ML startups.
  2. Extract company names and domains from results.
  3. For each new company, probe public ATS API endpoints to detect if they
     use Greenhouse, Lever, or Ashby (these need zero new scraper code).
  4. Auto-add ATS-hosted companies to config/companies.json.
  5. Flag non-ATS companies in config/pending_review.json for manual review.
  6. Log a summary of discoveries.

Usage:
    python -m scripts.discover_startups
    python -m scripts.discover_startups --search "ai startups pune 2026"
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# ── Path bootstrap ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("discover_startups")

# ── Config paths ──────────────────────────────────────────────────────────────
COMPANIES_JSON = _ROOT / "config" / "companies.json"
PENDING_REVIEW_JSON = _ROOT / "config" / "pending_review.json"

# ── Search queries for discovery ─────────────────────────────────────────────
DEFAULT_SEARCH_QUERIES = [
    "ai startups pune funding 2026",
    "machine learning company pune hiring",
    "tech startups pune india series a b",
    "ai ml company india new funding",
    "data science startup pune",
    "software startup pune ai hiring",
]

# ── ATS detection endpoints ──────────────────────────────────────────────────
ATS_PROBES = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://jobs.ashbyhq.com/api/non-user-graphql",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def search_google_news_rss(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Google News RSS for articles matching the query.
    Returns a list of {title, link, snippet} dicts.
    """
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[Discovery] Google News RSS search failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.content, "lxml-xml")
    items = soup.find_all("item", limit=max_results)

    results = []
    for item in items:
        title = item.title.text if item.title else ""
        link = item.link.text if item.link else ""
        desc = item.description.text if item.description else ""
        results.append({"title": title, "link": link, "snippet": desc})

    logger.info("[Discovery] Query %r → %d articles", query, len(results))
    return results


def extract_company_names(articles: list[dict]) -> list[dict]:
    """
    Extract potential company names and domains from article titles/snippets.
    Uses heuristics to identify company names mentioned in tech/funding news.
    """
    # Common patterns in funding/hiring news headlines
    patterns = [
        # "CompanyName raises $X million"
        r"(?:^|\b)([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\s+(?:raises|secures|closes|gets|bags)",
        # "CompanyName, a ... startup"
        r"(?:^|\b)([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2}),?\s+(?:a|an)\s+.*?(?:startup|company)",
        # "... at CompanyName"
        r"(?:hiring|jobs|openings|careers)\s+(?:at|with)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})",
        # "CompanyName is hiring"
        r"(?:^|\b)([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\s+(?:is\s+)?hiring",
    ]

    # Words to exclude (common false positives)
    exclude_words = {
        "India", "Pune", "Mumbai", "Bangalore", "Delhi", "Hyderabad", "Chennai",
        "Series", "Round", "Funding", "The", "This", "That", "And", "For",
        "Google", "Microsoft", "Amazon", "Meta", "Apple",  # too big
        "AI", "ML", "Tech", "Data", "New", "Top", "Best",
    }

    found = {}  # name -> {name, domain_guess, source_article}
    compiled = [re.compile(p, re.MULTILINE) for p in patterns]

    for article in articles:
        text = f"{article['title']} {article['snippet']}"
        for pattern in compiled:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                if name in exclude_words or len(name) < 3:
                    continue
                if name not in found:
                    slug_guess = name.lower().replace(" ", "").replace(".", "")
                    found[name] = {
                        "name": name,
                        "slug_guess": slug_guess,
                        "source_article": article["title"][:100],
                    }

    logger.info("[Discovery] Extracted %d potential company names", len(found))
    return list(found.values())


def probe_ats(slug: str) -> Optional[str]:
    """
    Probe known ATS API endpoints to detect which platform a company uses.
    Returns the ats_type string ('greenhouse', 'lever', 'ashby') or None.
    """
    # 1. Try Greenhouse
    try:
        url = ATS_PROBES["greenhouse"].format(slug=slug)
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "jobs" in data:
                logger.info("[ATS Probe] %s → Greenhouse ✓", slug)
                return "greenhouse"
    except Exception:
        pass

    time.sleep(0.5)

    # 2. Try Lever
    try:
        url = ATS_PROBES["lever"].format(slug=slug)
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                logger.info("[ATS Probe] %s → Lever ✓", slug)
                return "lever"
    except Exception:
        pass

    time.sleep(0.5)

    # 3. Try Ashby
    try:
        url = ATS_PROBES["ashby"]
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { "
                     "jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { "
                     "teams { id name } } }",
        }
        resp = requests.post(
            url,
            json=payload,
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data", {}).get("jobBoard"):
                logger.info("[ATS Probe] %s → Ashby ✓", slug)
                return "ashby"
    except Exception:
        pass

    return None


def load_existing_companies() -> set[str]:
    """Load existing company names from companies.json (lowercased for comparison)."""
    if not COMPANIES_JSON.exists():
        return set()
    with open(COMPANIES_JSON, "r", encoding="utf-8") as f:
        companies = json.load(f)
    return {c["name"].lower() for c in companies}


def load_pending_review() -> list[dict]:
    """Load existing pending review entries."""
    if not PENDING_REVIEW_JSON.exists():
        return []
    with open(PENDING_REVIEW_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_companies(companies: list[dict]):
    """Save the updated companies list."""
    with open(COMPANIES_JSON, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)
        f.write("\n")


def save_pending_review(entries: list[dict]):
    """Save the pending review list."""
    with open(PENDING_REVIEW_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run_discovery(search_queries: list[str] | None = None, dry_run: bool = False):
    """
    Main discovery flow.
    """
    queries = search_queries or DEFAULT_SEARCH_QUERIES
    existing = load_existing_companies()

    logger.info("=" * 70)
    logger.info("Startup Discovery — %s", datetime.now(timezone.utc).isoformat())
    logger.info("=" * 70)

    # 1. Search for articles
    all_articles = []
    for query in queries:
        articles = search_google_news_rss(query)
        all_articles.extend(articles)
        time.sleep(1)  # Be polite

    if not all_articles:
        logger.warning("[Discovery] No articles found — nothing to discover.")
        return

    # 2. Extract company names
    candidates = extract_company_names(all_articles)

    # Filter out companies already in companies.json
    new_candidates = [
        c for c in candidates
        if c["name"].lower() not in existing
    ]
    logger.info(
        "[Discovery] %d candidates after removing %d already-known companies",
        len(new_candidates), len(candidates) - len(new_candidates),
    )

    if not new_candidates:
        logger.info("[Discovery] No new companies found this run.")
        return

    # 3. Probe each candidate
    auto_added = []
    pending = load_pending_review()
    pending_names = {p["name"].lower() for p in pending}

    with open(COMPANIES_JSON, "r", encoding="utf-8") as f:
        companies_list = json.load(f)

    for candidate in new_candidates:
        name = candidate["name"]
        slug = candidate["slug_guess"]

        if name.lower() in pending_names:
            logger.debug("[Discovery] %s already in pending_review — skipping", name)
            continue

        logger.info("[Discovery] Probing ATS for %s (slug guess: %s)...", name, slug)
        ats_type = probe_ats(slug)

        if ats_type:
            # Auto-add to companies.json
            new_entry = {
                "name": name,
                "ats_type": ats_type,
                "identifier": slug,
                "location_priority": "india",
                "enabled": True,
                "notes": f"Auto-discovered on {datetime.now().strftime('%Y-%m-%d')} from: {candidate['source_article']}",
            }
            if not dry_run:
                companies_list.append(new_entry)
            auto_added.append(new_entry)
            logger.info(
                "[Discovery] ✅ Auto-added: %s (%s) to companies.json", name, ats_type,
            )
        else:
            # Flag for manual review
            review_entry = {
                "name": name,
                "slug_guess": slug,
                "source_article": candidate["source_article"],
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "notes": "No ATS detected — may need a custom scraper.",
            }
            if not dry_run:
                pending.append(review_entry)
                pending_names.add(name.lower())
            logger.info("[Discovery] ⏳ Flagged for review: %s", name)

        time.sleep(1)  # Be polite between probes

    # 4. Save results
    if not dry_run:
        if auto_added:
            save_companies(companies_list)
        save_pending_review(pending)

    # 5. Log summary
    logger.info("=" * 70)
    logger.info("╔═══ DISCOVERY SUMMARY ═══╗")
    logger.info("║ Articles searched:    %4d", len(all_articles))
    logger.info("║ Candidates found:     %4d", len(candidates))
    logger.info("║ New candidates:       %4d", len(new_candidates))
    logger.info("║ Auto-added (ATS):     %4d", len(auto_added))
    logger.info("║ Flagged for review:   %4d", len(pending) - len(load_pending_review()) if not dry_run else 0)
    logger.info("╚═════════════════════════╝")
    if auto_added:
        logger.info("Auto-added companies:")
        for entry in auto_added:
            logger.info("  ✅ %s (%s)", entry["name"], entry["ats_type"])
    logger.info("=" * 70)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Discover new tech startups in Pune/India for the AI Job Hunter agent.",
    )
    parser.add_argument(
        "--search",
        type=str,
        nargs="*",
        default=None,
        help="Custom search queries (space-separated). Overrides defaults.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery without modifying any files.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    run_discovery(
        search_queries=args.search,
        dry_run=args.dry_run,
    )
