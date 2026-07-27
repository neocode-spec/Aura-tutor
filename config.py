"""
config.py — Curriculum data, exam levels, and Alpha model tiers for Iris
"""

# -----------------------------------------------------------------------------
# Streams & Subjects (Nigerian secondary curriculum)
# -----------------------------------------------------------------------------
CORE_SUBJECTS = ["Mathematics", "English Language", "Civic Education"]

SCIENCE_SUBJECTS = [
    "Physics", "Chemistry", "Biology", "Further Mathematics",
    "Agricultural Science", "Computer Science", "Geography", "Health Science",
]

ARTS_SUBJECTS = [
    "Literature in English", "Government", "History",
    "Christian Religious Studies (CRS)", "Islamic Religious Studies (IRS)",
    "French", "Yoruba", "Igbo", "Hausa", "Fine Arts", "Music",
]

SOCIAL_SCIENCE_SUBJECTS = [
    "Economics", "Government", "Commerce", "Financial Accounting",
    "Geography", "Christian Religious Studies (CRS)", "Islamic Religious Studies (IRS)",
]

STREAMS = {
    "Science": SCIENCE_SUBJECTS,
    "Arts": ARTS_SUBJECTS,
    "Social Science": SOCIAL_SCIENCE_SUBJECTS,
}


def subjects_for_stream(stream: str):
    """Core subjects + stream-specific subjects, de-duplicated, sorted."""
    combined = set(CORE_SUBJECTS) | set(STREAMS.get(stream, []))
    return sorted(combined)


# -----------------------------------------------------------------------------
# Target Exam / Level
# -----------------------------------------------------------------------------
EXAM_LEVELS = [
    "WAEC / SSCE",
    "JAMB / UTME",
    "NECO",
    "Common Entrance",
    "Post-UTME",
    "General Classwork / Homework",
]

# -----------------------------------------------------------------------------
# Alpha Model Tiers
# Groq model IDs — verify current names at console.groq.com/docs/models,
# Groq deprecates/renames models periodically.
# -----------------------------------------------------------------------------
MODEL_TIERS = {
    "Iris Alpha": {
        "model": "llama-3.1-8b-instant",
        "price_ngn": 0,
        "billing": "free",
        "description": "Fast, solid for everyday practice and quick questions.",
        "daily_question_limit": 15,
    },
    "Iris Alpha+": {
        "model": "llama-3.3-70b-versatile",
        "price_ngn": 1000,
        "billing": "monthly",
        "description": "Stronger reasoning — better for WAEC/JAMB-depth explanations.",
        "daily_question_limit": None,
    },
    "Iris Alpha Ultimate": {
        "model": "openai/gpt-oss-120b",
        "price_ngn": 2500,
        "billing": "monthly",
        "description": "Top-tier reasoning — tough concepts, past-question breakdowns, exam strategy.",
        "daily_question_limit": None,
    },
}

FREE_TIER_NAME = "Iris Alpha"
