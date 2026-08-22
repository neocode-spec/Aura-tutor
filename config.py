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
    "Aura Alpha": {
        "model": "openai/gpt-oss-20b",
        "price_ngn": 0,
        "billing": "free",
        "description": "Free — solid everyday tutor, longer answers allowed.",
        "daily_question_limit": 30,
        "max_tokens": 2048,
    },
    "Aura Alpha+": {
        "model": "openai/gpt-oss-120b",
        "price_ngn": 500,
        "billing": "monthly",
        "description": "Stronger reasoning — 9 full-power requests/day, then falls back to Alpha.",
        "daily_question_limit": None,       # never blocked
        "premium_daily_limit": 9,           # full-model requests/day before falling back
        "max_tokens": 3072,
    },
}

FREE_TIER_NAME = "Aura Alpha"
