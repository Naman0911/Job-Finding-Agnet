"""
tests/test_filters.py
Tests for location_filter and role_filter pipeline stages.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pipeline.location_filter import is_accepted_location, filter_jobs as location_filter_jobs
from pipeline.role_filter import matches_role_whitelist, filter_jobs as role_filter_jobs


# ── Location filter tests ─────────────────────────────────────────────────────

class TestLocationFilter:

    # ── Should ACCEPT ──────────────────────────────────────────────────────────
    @pytest.mark.parametrize("loc", [
        "Pune",
        "Pune, India",
        "India",
        "India (Remote)",
        "Remote - India",
        "Remote - india",
        "Remote (India)",
        "remote - india",
        "Pan India",
        "Pan-India",
        "pan india",
        "Bangalore, India",    # contains "india"
        "Mumbai, India",
        "Hyderabad, India",
        "",                     # empty → permissive accept
    ])
    def test_accepted_locations(self, loc):
        assert is_accepted_location(loc), f"Should accept: {loc!r}"

    # ── Should REJECT ──────────────────────────────────────────────────────────
    @pytest.mark.parametrize("loc", [
        "Remote",             # bare remote — no country
        "San Francisco, CA",
        "New York",
        "London, UK",
        "United Kingdom",
        "Singapore",
        "United States",
        "Germany",
        "Australia",
        "Dubai",
    ])
    def test_rejected_locations(self, loc):
        assert not is_accepted_location(loc), f"Should reject: {loc!r}"

    def test_filter_jobs_keeps_india(self):
        jobs = [
            {"title": "DS", "location": "Pune"},
            {"title": "ML", "location": "Remote - India"},
            {"title": "SWE", "location": "San Francisco"},
        ]
        result = location_filter_jobs(jobs)
        assert len(result) == 2
        titles = [j["title"] for j in result]
        assert "DS" in titles
        assert "ML" in titles

    def test_filter_jobs_empty_list(self):
        assert location_filter_jobs([]) == []


# ── Role filter tests ─────────────────────────────────────────────────────────

class TestRoleFilter:

    # ── Should MATCH (keep) ────────────────────────────────────────────────────
    @pytest.mark.parametrize("title", [
        "Data Scientist",
        "Senior Data Scientist",
        "Data Science Lead",
        "Machine Learning Engineer",
        "ML Engineer",
        "MLE",
        "Staff MLE",
        "AI Engineer",
        "Applied Scientist",
        "GenAI Engineer",
        "Gen-AI Researcher",
        "LLM Engineer",
        "NLP Engineer",
        "Data Analyst",
        "Senior Data Analyst",
        "Analytics Engineer",
        "MLOps Engineer",
        "AI Research Scientist",
        "AI Research Intern",
        "ML Intern",
        "Deep Learning Engineer",
        "Computer Vision Engineer",
        "Natural Language Processing Researcher",
        "Data Engineer",
        "Data Engineering Manager",
        # v3+v9: Software roles are now whitelisted
        "Software Engineer",
        "Backend Developer",
        "Frontend Engineer",
        "DevOps Engineer",
        # v9 additions
        "Research Engineer",
        "Prompt Engineer",
        "Python Developer",
        "QA Engineer",
        "SDET",
        "Infrastructure Engineer",
    ])
    def test_matched_titles(self, title):
        assert matches_role_whitelist(title), f"Should match: {title!r}"

    # ── Should NOT MATCH (drop) ────────────────────────────────────────────────
    @pytest.mark.parametrize("title", [
        "Product Manager",
        "Data Entry Analyst",    # false positive guard
        "AI Product Manager",
        "Business Analyst",
        "Sales Manager",
        "UX Designer",
    ])
    def test_unmatched_titles(self, title):
        assert not matches_role_whitelist(title), f"Should NOT match: {title!r}"

    def test_case_insensitive(self):
        assert matches_role_whitelist("DATA SCIENTIST")
        assert matches_role_whitelist("machine learning engineer")
        assert matches_role_whitelist("Llm Researcher")

    def test_filter_jobs_bulk(self):
        jobs = [
            {"title": "Data Scientist", "location": "Pune"},
            {"title": "ML Engineer", "location": "India"},
            {"title": "Software Engineer", "location": "Pune"},
            {"title": "Sales Executive", "location": "India"},
            {"title": "LLM Researcher", "location": "India"},
        ]
        result = role_filter_jobs(jobs)
        assert len(result) == 4  # DS, ML, SWE, LLM (Sales dropped)
        kept_titles = {j["title"] for j in result}
        assert "Data Scientist" in kept_titles
        assert "ML Engineer" in kept_titles
        assert "Software Engineer" in kept_titles  # v3+: now whitelisted
        assert "LLM Researcher" in kept_titles

    def test_filter_empty_list(self):
        assert role_filter_jobs([]) == []
