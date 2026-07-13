"""
scheduler/run.py
Main pipeline orchestrator for the AI Job Hunter agent (v3).

v3 changes:
  - Dropped Telegram and WhatsApp notifiers — email only
  - Added aggregator scraper routing (naukri, instahyre, cutshort, wellfound)
  - Enhanced per-run summary logging
  - Default schedule interval: 6 hours

Pipeline (per run):
  1. Load company config
  2. For each company/source: scrape → RawJob list
  3. Normalise all RawJobs → Job dicts
  4. Location filter (Pune/India only)
  5. Role keyword filter (DS/AI-ML + SDE titles)
  6. LLM relevance double-check (Gemini Flash)
  7. Dedup against seen hashes in DB
  8. Insert new jobs into DB
  9. Send email notifications for new jobs
  10. Mark jobs as notified
  11. Log run stats

Can be run:
  - Directly:  python -m scheduler.run
  - Scheduled: via APScheduler (if RUN_MODE=scheduled)
  - GitHub Actions: via cron in .github/workflows/run_agent.yml
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Path bootstrap (run from project root or as module) ───────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from config.settings import settings
from database.db import JobDatabase
from notifier.email_notifier import EmailNotifier
from pipeline import location_filter, role_filter, dedup, experience_filter
from pipeline.normalizer import normalise
from pipeline.llm_classifier import LLMClassifier
from pipeline.semantic_classifier import SemanticClassifier
from scrapers.base_scraper import RawJob


# ── Logging setup ─────────────────────────────────────────────────────────────
def setup_logging(level: str = "INFO"):
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format=fmt)
    # Quieten noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


logger = logging.getLogger("scheduler.run")


# ── Scraper factory ──────────────────────────────────────────────────────────
def build_scraper(company: dict):
    """
    Instantiate the right scraper class for a company config entry.
    Returns None if ats_type is unknown or company is disabled.
    """
    if not company.get("enabled", True):
        return None

    ats_type = company.get("ats_type", "").lower()
    name = company["name"]
    identifier = company.get("identifier", "")

    if ats_type == "greenhouse":
        from scrapers.greenhouse import GreenhouseScraper
        return GreenhouseScraper(name, identifier)

    elif ats_type == "lever":
        from scrapers.lever import LeverScraper
        return LeverScraper(name, identifier)

    elif ats_type == "ashby":
        from scrapers.ashby import AshbyScraper
        return AshbyScraper(name, identifier)

    elif ats_type == "custom":
        return _build_custom_scraper(name)

    # ── Aggregator sources (v3) ──────────────────────────────────────────────
    elif ats_type == "naukri":
        from scrapers.naukri import NaukriScraper
        return NaukriScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "pune"),
        )

    elif ats_type == "instahyre":
        from scrapers.instahyre import InstahyreScraper
        return InstahyreScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "pune"),
        )

    elif ats_type == "cutshort":
        from scrapers.cutshort import CutshortScraper
        return CutshortScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "pune"),
        )

    elif ats_type == "wellfound":
        from scrapers.wellfound import WellfoundScraper
        return WellfoundScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "india"),
        )

    # ── Additional aggregator sources (v9) ───────────────────────────────────
    elif ats_type == "indeed":
        from scrapers.indeed import IndeedScraper
        return IndeedScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "Pune, Maharashtra"),
        )

    elif ats_type == "glassdoor":
        from scrapers.glassdoor import GlassdoorScraper
        return GlassdoorScraper(
            company_name=name,
            identifier=identifier,
            search_location=company.get("search_location", "pune"),
        )

    else:
        logger.warning("[Factory] Unknown ats_type %r for %r — skipping", ats_type, name)
        return None


def _build_custom_scraper(name: str):
    """Route to the right custom scraper by company name."""
    custom_map = {
        "Chargebee": lambda: _import_and_instantiate("scrapers.custom.chargebee", "ChargebeeScraper"),
        "BrowserStack": lambda: _import_and_instantiate("scrapers.custom.browserstack", "BrowserStackScraper"),
        "Freshworks": lambda: _import_and_instantiate("scrapers.custom.freshworks", "FreshworksScraper"),
        "Persistent Systems": lambda: _import_and_instantiate("scrapers.custom.persistent", "PersistentScraper"),
        "Talentica": lambda: _import_and_instantiate("scrapers.custom.talentica", "TalenicaScraper"),
        "Datametica": lambda: _import_and_instantiate("scrapers.custom.datametica", "DatameticaScraper"),
        "FlytBase": lambda: _import_and_instantiate("scrapers.custom.flytbase", "FlytBaseScraper"),
        "Sarvam AI": lambda: _import_and_instantiate("scrapers.custom.sarvam", "SarvamScraper"),
        "Fractal Analytics": lambda: _import_and_instantiate("scrapers.custom.fractal", "FractalScraper"),
    }
    factory = custom_map.get(name)
    if factory:
        return factory()
    logger.warning("[Factory] No custom scraper registered for %r", name)
    return None


def _import_and_instantiate(module_path: str, class_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


# ── Notifier factory (v3: EMAIL ONLY) ────────────────────────────────────────
def build_notifiers() -> list:
    """Build the list of active notifiers. v3: email is the only channel."""
    notifiers = []
    em = EmailNotifier()
    if em.enabled:
        notifiers.append(em)
        logger.info("[Pipeline] Email notifier enabled → %s", em.to_addrs)
    else:
        logger.warning(
            "[Pipeline] Email notifier not configured! "
            "Set SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO in .env"
        )
    return notifiers


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(dry_run: bool = False) -> dict:
    """
    Execute one full pipeline pass.

    Args:
        dry_run: If True, run the whole pipeline but don't insert to DB or notify.

    Returns:
        Stats dict with run results.
    """
    start = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("AI Job Hunter v3 — pipeline run started at %s", start.isoformat())
    if dry_run:
        logger.info("DRY RUN MODE — no DB writes, no notifications")
    logger.info("=" * 70)

    stats = {
        "companies_count": 0,
        "jobs_scraped": 0,
        "jobs_after_location": 0,
        "jobs_after_role": 0,
        "jobs_after_experience": 0,
        "jobs_after_llm": 0,
        "jobs_new": 0,
        "jobs_notified": 0,
        "errors": [],
    }

    # Load companies
    companies = _load_companies()
    enabled = [c for c in companies if c.get("enabled", True)]
    stats["companies_count"] = len(enabled)
    logger.info("[Pipeline] %d sources enabled (companies + aggregators)", len(enabled))

    # Initialise LLM classifier and Semantic classifier
    classifier = LLMClassifier(model=settings.llm_model)
    semantic_classifier = SemanticClassifier()

    # Build notifiers
    notifiers = build_notifiers() if not dry_run else []

    # ── Scrape phase (Parallel Execution) ────────────────────────────────────
    all_raw: list[RawJob] = []

    def scrape_one(company: dict) -> tuple[str, list[RawJob] | Exception]:
        scraper = build_scraper(company)
        if scraper is None:
            return company["name"], []
        try:
            raw_jobs = scraper.fetch()
            return company["name"], raw_jobs
        except Exception as exc:
            return company["name"], exc

    logger.info("[Pipeline] Starting parallel scrape (max_workers=5)...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_one, company): company for company in enabled}
        for future in as_completed(futures):
            company = futures[future]
            try:
                name, result = future.result()
                if isinstance(result, Exception):
                    msg = f"{name}: {result}"
                    logger.error("[Scrape] FAILED — %s", msg)
                    stats["errors"].append(msg)
                else:
                    logger.info("[Scrape] %s → %d raw jobs", name, len(result))
                    all_raw.extend(result)
            except Exception as exc:
                msg = f"{company['name']}: {exc}"
                logger.error("[Scrape] FAILED — %s", msg)
                stats["errors"].append(msg)

    stats["jobs_scraped"] = len(all_raw)
    logger.info("[Pipeline] Total raw jobs fetched: %d", len(all_raw))

    # ── Normalise ─────────────────────────────────────────────────────────────
    normalised = [normalise(r) for r in all_raw]

    # ── Pipeline filtering + DB + LLM ─────────────────────────────────────────
    with JobDatabase(settings.db_path) as db:
        run_id = None if dry_run else db.log_run_start()

        # 1. Location filter
        loc_filtered = location_filter.filter_jobs(normalised)
        stats["jobs_after_location"] = len(loc_filtered)
        logger.info("[Pipeline] After location filter: %d (dropped %d)",
                    len(loc_filtered), len(normalised) - len(loc_filtered))

        # 2. Role keyword filter
        role_filtered = role_filter.filter_jobs(loc_filtered)
        stats["jobs_after_role"] = len(role_filtered)
        logger.info("[Pipeline] After role filter: %d (dropped %d)",
                    len(role_filtered), len(loc_filtered) - len(role_filtered))

        # 3. Dedup (moved up)
        new_jobs_candidates = dedup.filter_new_jobs(role_filtered, db)
        logger.info("[Pipeline] After dedup: %d (already seen %d)",
                    len(new_jobs_candidates), len(role_filtered) - len(new_jobs_candidates))

        # 4. Hybrid Relevance & Experience Pass
        final_jobs = []
        auto_accepted = 0
        auto_rejected = 0
        llm_checked = 0
        llm_rejected = 0

        for job in new_jobs_candidates:
            # Experience classification
            exp_acc, exp_rej, exp_amb = experience_filter.classify(job)
            
            # Semantic classification
            sem_acc, sem_rej, sem_amb = semantic_classifier.classify(job)
            
            # Hybrid logic
            if exp_rej or sem_rej:
                auto_rejected += 1
                logger.debug(f"[HybridFilter] Auto-rejected: '{job['title']}' (ExpREJ:{exp_rej}, SemREJ:{sem_rej})")
                continue
                
            if exp_amb or sem_amb:
                llm_checked += 1
                # Fallback to LLM
                is_relevant = classifier.is_relevant(job['title'], job.get('description_snippet', ''), db=db if not dry_run else None)
                if is_relevant:
                    final_jobs.append(job)
                else:
                    llm_rejected += 1
                    logger.debug(f"[HybridFilter] LLM rejected: '{job['title']}'")
            else:
                # Both accepted
                auto_accepted += 1
                final_jobs.append(job)

        stats["jobs_after_experience"] = len(final_jobs)  # combined stat
        stats["jobs_after_llm"] = len(final_jobs)
        stats["jobs_new"] = len(final_jobs)
        
        logger.info(f"[HybridFilter] Auto-accepted: {auto_accepted}, Auto-rejected: {auto_rejected}, LLM-checked: {llm_checked} (LLM rejected {llm_rejected})")
        logger.info("[Pipeline] Final new jobs: %d", len(final_jobs))

        if not final_jobs:
            logger.info("[Pipeline] No relevant new jobs found this run")
            if not dry_run:
                db.log_run_end(run_id, companies_count=stats["companies_count"], jobs_scraped=stats["jobs_scraped"])
            _log_run_summary(stats, start, dry_run, db)
            return stats

        if dry_run:
            logger.info("[DRY RUN] Would insert %d jobs and notify", len(final_jobs))
            for job in final_jobs:
                logger.info("  → %s @ %s (%s) [source: %s]",
                            job["title"], job["company"], job["location"],
                            job.get("source", "?"))
            _log_run_summary(stats, start, dry_run, db)
            return stats

        # Insert into DB
        inserted = db.insert_jobs(final_jobs)
        logger.info("[DB] Inserted %d new jobs", inserted)

        # Notify via Digest
        if settings.notify_enabled:
            jobs_to_notify = []
            for job in final_jobs:
                job_row = _fetch_job_by_hash(db, job["dedup_hash"])
                if job_row:
                    job["id"] = job_row["id"]
                    jobs_to_notify.append(job)

            if jobs_to_notify:
                success = True
                for notifier in notifiers:
                    ok = notifier.send_digest(jobs_to_notify)
                    success = success and ok

                if success:
                    notified_ids = [j["id"] for j in jobs_to_notify]
                    db.mark_notified(notified_ids)
                    stats["jobs_notified"] = len(notified_ids)
                    logger.info("[Pipeline] Notified: %d jobs via email digest", len(notified_ids))
        else:
            logger.info("[Pipeline] Notifications disabled (NOTIFY_ENABLED=false)")

        # Log run
        db.log_run_end(
            run_id,
            companies_count=stats["companies_count"],
            jobs_scraped=stats["jobs_scraped"],
            jobs_new=stats["jobs_new"],
            jobs_notified=stats["jobs_notified"],
            errors="; ".join(stats["errors"]),
        )
        
        _log_run_summary(stats, start, dry_run, db)

    return stats


def _load_companies() -> list[dict]:
    config_path = settings.companies_config
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fetch_job_by_hash(db: JobDatabase, dedup_hash: str) -> Optional[dict]:
    cur = db._conn.execute(
        "SELECT * FROM jobs WHERE dedup_hash=?", (dedup_hash,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _log_run_summary(stats: dict, start: datetime, dry_run: bool, db: JobDatabase = None):
    """Log a comprehensive per-run summary (v3: per Change 3 requirement)."""
    end = datetime.now(timezone.utc)
    duration = (end - start).total_seconds()
    
    llm_calls_today = db.get_llm_calls_today() if db else 0

    logger.info("=" * 70)
    logger.info("╔═══ RUN SUMMARY %s═══╗", "(DRY RUN) " if dry_run else "")
    logger.info("║ Sources scraped:       %4d", stats["companies_count"])
    logger.info("║ Total jobs fetched:    %4d", stats["jobs_scraped"])
    logger.info("║ After location filter: %4d", stats["jobs_after_location"])
    logger.info("║ After role filter:     %4d", stats["jobs_after_role"])
    logger.info("║ After exp/sem filter:  %4d", stats["jobs_after_experience"])
    logger.info("║ New (unseen) jobs:     %4d", stats["jobs_new"])
    logger.info("║ Notified:             %4d", stats["jobs_notified"])
    logger.info("║ Errors:               %4d", len(stats["errors"]))
    logger.info("║ Duration:          %6.1fs", duration)
    logger.info("║ Gemini calls today:   %4d/1500", llm_calls_today)
    logger.info("╚══════════════════════════════╝")
    if stats["errors"]:
        for err in stats["errors"]:
            logger.warning("  ⚠ %s", err)
    logger.info("=" * 70)


# ── Scheduler mode ────────────────────────────────────────────────────────────
def run_scheduled():
    """
    Run the pipeline on a repeating schedule using APScheduler.
    Interval is configured via RUN_INTERVAL_HOURS env var (default: 6).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    interval_hours = settings.run_interval_hours
    logger.info("[Scheduler] Starting — will run every %d hours", interval_hours)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run_pipeline,
        trigger=IntervalTrigger(hours=interval_hours),
        id="job_hunter",
        name="AI Job Hunter Pipeline",
        misfire_grace_time=300,  # allow up to 5-min slip
        coalesce=True,           # only run once if multiple misfires
    )

    # Also run once immediately on startup
    logger.info("[Scheduler] Running pipeline immediately on startup...")
    run_pipeline()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("[Scheduler] Stopped by user")
        scheduler.shutdown()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Job Hunter Agent v3")
    parser.add_argument(
        "--mode",
        choices=["once", "scheduled", "dry-run"],
        default="once",
        help=(
            "once      = run pipeline once and exit\n"
            "scheduled = run on a repeating interval (APScheduler)\n"
            "dry-run   = run pipeline without DB writes or notifications"
        ),
    )
    parser.add_argument("--log-level", default=None, help="Override LOG_LEVEL")
    args = parser.parse_args()

    log_level = args.log_level or settings.log_level
    setup_logging(log_level)

    if args.mode == "dry-run":
        run_pipeline(dry_run=True)
    elif args.mode == "scheduled":
        run_scheduled()
    else:
        run_pipeline(dry_run=settings.dry_run)
