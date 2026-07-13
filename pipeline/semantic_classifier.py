"""
pipeline/semantic_classifier.py
Local semantic classifier using sentence-transformers.
"""
import logging
from typing import Tuple

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    SentenceTransformer = None

from config.settings import settings

logger = logging.getLogger(__name__)

# References for matching
POSITIVE_ROLES = [
    # ── Original ─────────────────────────────────────────────────────────────
    "Data Scientist",
    "Machine Learning Engineer",
    "Applied Scientist",
    "GenAI Engineer",
    "LLM Engineer",
    "Data Analyst",
    "MLOps Engineer",
    "Software Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full-stack Developer",
    "Mobile Developer",
    "SDE",
    "Member of Technical Staff",
    # ── v9 DS/AI-ML additions ────────────────────────────────────────────────
    "Data Engineer",
    "Research Engineer",
    "Computer Vision Engineer",
    "CV Engineer",
    "NLP Engineer",
    "Prompt Engineer",
    "AI Research Intern",
    "Research Intern",
    "Quantitative Analyst",
    "Quant Researcher",
    "Data Science Intern",
    "ML Research Engineer",
    "Applied AI Engineer",
    "Generative AI Engineer",
    "Data Platform Engineer",
    "Deep Learning Engineer",
    # ── v9 SDE additions ─────────────────────────────────────────────────────
    "Software Development Engineer",
    "SDE Intern",
    "Programmer Analyst",
    "Python Developer",
    "Java Developer",
    "React Developer",
    "Node Developer",
    "Golang Developer",
    "Site Reliability Engineer",
    "SRE",
    "QA Engineer",
    "SDET",
    "Cloud Engineer",
    "Platform Engineer",
    "Systems Engineer",
    "Infrastructure Engineer",
    "DevOps Engineer",
]

NEGATIVE_ROLES = [
    "Data Entry Analyst",
    "Senior Data Scientist",
    "Lead Software Engineer",
    "Principal Engineer",
    "Staff Engineer",
    "Engineering Manager",
    "Director of Engineering",
    "Sales Executive",
    "Marketing Manager",
    "HR Associate",
    "Recruiter",
    "Product Manager",
    "Project Manager",
    "Technical Support",
    "Business Analyst",
]

class SemanticClassifier:
    def __init__(self):
        if SentenceTransformer is None:
            logger.warning("[SemanticClassifier] sentence-transformers not installed. Skipping local classifier.")
            self.model = None
            return

        logger.info("[SemanticClassifier] Loading model 'all-MiniLM-L6-v2' (this may take a moment on first run)...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Pre-compute reference embeddings
        self.pos_emb = self.model.encode(POSITIVE_ROLES, convert_to_tensor=True)
        self.neg_emb = self.model.encode(NEGATIVE_ROLES, convert_to_tensor=True)
        logger.info("[SemanticClassifier] Model loaded and references embedded.")

    def classify(self, job: dict) -> Tuple[bool, bool, bool]:
        """
        Evaluates a job using cosine similarity.
        Returns: (is_auto_accepted, is_auto_rejected, is_ambiguous)
        """
        if self.model is None:
            # Fallback to ambiguous if not installed
            return False, False, True

        text = job.get("title", "")
        if job.get("description_snippet"):
            # Use title and first bit of snippet
            text += f" - {job['description_snippet'][:200]}"
            
        emb = self.model.encode(text, convert_to_tensor=True)

        # Compute max similarities
        pos_scores = util.cos_sim(emb, self.pos_emb)[0]
        neg_scores = util.cos_sim(emb, self.neg_emb)[0]
        
        max_pos = float(pos_scores.max())
        max_neg = float(neg_scores.max())
        
        score = max_pos - max_neg
        
        upper = settings.semantic_upper_threshold
        lower = settings.semantic_lower_threshold
        
        logger.debug(f"[SemanticClassifier] '{job.get('title')}' -> pos: {max_pos:.3f}, neg: {max_neg:.3f}, score: {score:.3f}")
        
        if score > upper:
            return True, False, False  # Auto-accept
        elif score < lower:
            return False, True, False  # Auto-reject
        else:
            return False, False, True  # Ambiguous
