"""
pipeline/llm_classifier.py
Uses Gemini Flash (free tier) to do a yes/no relevance check on job titles.

v3 changes:
  - Updated classification prompt to include Software Development roles:
    "Is this job primarily Data Science, AI/ML, GenAI/LLM, MLOps, Data Analyst work,
     OR mainstream Software/Backend/Frontend/Full-stack/Mobile development?"

The LLM pass catches:
  - Ambiguous titles that the keyword filter missed (e.g. "Software Engineer - AI Platform")
  - False positives the keyword filter let through (e.g. "Data Entry Analyst")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt (v3: broadened to include SDE roles) ───────────────────────────────
CLASSIFY_PROMPT = """You are a hiring classifier. Given this job title and description, and a candidate profile of: final-year student graduating in 2027, ~6 months of internship experience, no full-time work experience — is this role something they could reasonably apply to (fresher/entry-level/internship/associate, or a role with no strict minimum-experience requirement)? 

The role must also be primarily one of these categories:

Data Science / AI-ML umbrella:
  Data Scientist, Machine Learning Engineer, AI Engineer, Applied Scientist,
  GenAI/LLM Engineer, Prompt Engineer, NLP Engineer, Computer Vision Engineer,
  Research Engineer, MLOps, Data Analyst, Data Engineer, Data Platform Engineer,
  Quantitative Analyst, Quant Researcher, Deep Learning Engineer,
  AI/ML/Data Science Intern, Research Intern, Applied AI

Software Engineering umbrella:
  Software Engineer, SDE, Software Development Engineer, Backend Developer,
  Frontend Developer, Full-stack Developer, Mobile/Android/iOS Developer,
  DevOps Engineer, Cloud Engineer, Platform Engineer, SRE/Site Reliability Engineer,
  Systems Engineer, Infrastructure Engineer, QA Engineer, SDET,
  Python/Java/React/Node/Golang Developer, Programmer Analyst, SDE Intern

Answer ONLY with the single word "yes" or "no". No explanation.
Answer "yes" if it fits any of the tech categories above AND matches the experience profile.
Answer "no" if it's a non-technical role, a loosely adjacent tech role, or if it explicitly requires more experience than the candidate has.

Job title: {title}
Description snippet: {snippet}

Answer:"""


class LLMClassifier:
    """
    Wraps the Gemini API to classify whether a job is relevant.

    Usage:
        classifier = LLMClassifier()
        result = classifier.is_relevant("Machine Learning Engineer", "Build ML pipelines...")
    """

    def __init__(self, model: str = "gemini-1.5-flash-latest", request_delay: float = 0.5):
        self.model_name = model
        self.request_delay = request_delay
        self._client = None
        self._setup()

    def _setup(self):
        """Initialise Gemini client from GOOGLE_API_KEY env var."""
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not api_key or api_key == "your-gemini-api-key-here":
            logger.warning(
                "[LLMClassifier] GOOGLE_API_KEY not set or placeholder — LLM classification disabled. "
                "Jobs that pass keyword filter will be accepted without LLM check."
            )
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self.model_name)
            logger.info("[LLMClassifier] Gemini client initialised (%s)", self.model_name)
        except ImportError:
            logger.error(
                "[LLMClassifier] google-generativeai not installed. "
                "Run: pip install google-generativeai"
            )
        except Exception as exc:
            logger.error("[LLMClassifier] Setup failed: %s", exc)

    def is_relevant(self, title: str, snippet: str = "", db=None) -> bool:
        """
        Return True if the Gemini API says the job is relevant.
        Falls back to True (accept) if the API is unavailable.
        """
        if self._client is None:
            # No API key or client setup failed → accept all keyword-matched jobs
            return True

        prompt = CLASSIFY_PROMPT.format(
            title=title.strip(),
            snippet=(snippet or "")[:400].strip(),
        )

        for attempt in range(3):
            try:
                response = self._client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0,
                        "max_output_tokens": 5,
                    },
                )
                if db:
                    db.increment_llm_calls(1)
                
                answer = response.text.strip().lower()
                time.sleep(self.request_delay)
                if answer.startswith("yes"):
                    return True
                if answer.startswith("no"):
                    return False
                # Unexpected answer — log and accept
                logger.warning(
                    "[LLMClassifier] Unexpected answer %r for %r — defaulting to accept",
                    answer, title,
                )
                return True
            except Exception as exc:
                exc_str = str(exc)
                if any(k in exc_str.lower() for k in ["api_key_invalid", "api key not valid", "not found", "404", "permission", "invalid"]):
                    logger.error("[LLMClassifier] Permanent error encountered: %s. Disabling LLM classifier for this run.", exc_str)
                    self._client = None
                    return True

                wait = 2 ** attempt
                logger.warning(
                    "[LLMClassifier] Attempt %d failed for %r: %s — retrying in %ds",
                    attempt + 1, title, exc, wait,
                )
                time.sleep(wait)

        logger.error("[LLMClassifier] All retries failed for %r — defaulting to accept", title)
        return True  # fail-open: don't drop legitimate jobs on API errors

    def filter_jobs(self, jobs: list[dict]) -> list[dict]:
        """
        Run LLM classification on a list of normalised job dicts.
        Returns only those classified as relevant.
        """
        if self._client is None:
            logger.info("[LLMClassifier] Skipping LLM pass (no API key)")
            return jobs

        kept = []
        for job in jobs:
            title = job.get("title", "")
            snippet = job.get("description_snippet", "")
            relevant = self.is_relevant(title, snippet)
            if relevant:
                kept.append(job)
            else:
                logger.info("[LLMClassifier] Rejected: %r (%s)", title, job.get("company", ""))

        dropped = len(jobs) - len(kept)
        logger.info(
            "[LLMClassifier] kept %d / %d  (rejected %d by LLM)",
            len(kept), len(jobs), dropped,
        )
        return kept
