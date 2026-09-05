"""
db.py — Neon Postgres connection, schema, and memory helpers for Aura

Set NEON_DATABASE_URL in your environment or Render settings:
    postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require
"""

import os
import hashlib
import secrets as pysecrets
from datetime import date

import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor


def _get_secret(key: str, default: str = "") -> str:
    """Read from env var first, then Streamlit secrets if available (won't crash if no secrets.toml exists)."""
    value = os.getenv(key)
    if value:
        return value
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


NEON_DATABASE_URL = _get_secret("NEON_DATABASE_URL")


def get_connection():
    if not NEON_DATABASE_URL:
        raise RuntimeError("NEON_DATABASE_URL is not set.")
    return psycopg2.connect(NEON_DATABASE_URL, cursor_factory=RealDictCursor)


def init_schema():
    schema_sql = """
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        security_question TEXT,
        security_answer_hash TEXT,
        security_answer_salt TEXT,
        stream TEXT,
        tier TEXT DEFAULT 'Aura Alpha',
        tier_active_until DATE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        id SERIAL PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        subject TEXT,
        exam_level TEXT,
        role TEXT NOT NULL,          -- 'user' or 'assistant'
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS usage_log (
        id SERIAL PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        usage_date DATE DEFAULT CURRENT_DATE,
        question_count INTEGER DEFAULT 0,
        UNIQUE(student_id, usage_date)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        tx_ref TEXT UNIQUE NOT NULL,
        flw_transaction_id TEXT,
        tier TEXT NOT NULL,
        amount_ngn INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',   -- pending / successful / failed
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
        # Safe upgrades for tables that existed before these columns/tables
        # were added. Every statement here is IF NOT EXISTS, so this never
        # breaks on a fresh DB and never breaks on one that's already current.
        cur.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS security_question TEXT")
        cur.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS security_answer_hash TEXT")
        cur.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS security_answer_salt TEXT")
        # Rebrand migration: any student created back when tiers were named "Iris ..."
        cur.execute("UPDATE students SET tier = 'Aura Alpha' WHERE tier = 'Iris Alpha'")
        cur.execute("UPDATE students SET tier = 'Aura Alpha+' WHERE tier = 'Iris Alpha+'")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- security answer hashing --
def _hash_answer(answer: str, salt: str = None):
    """PBKDF2-HMAC-SHA256, 200k iterations. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = pysecrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", answer.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()
    return hashed, salt


def _verify_answer(answer: str, stored_hash: str, stored_salt: str) -> bool:
    if not stored_hash or not stored_salt:
        return False
    check_hash, _ = _hash_answer(answer, stored_salt)
    return pysecrets.compare_digest(check_hash, stored_hash)


# ---------------------------------------------------------------- students --
def find_student_by_email(email: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM students WHERE email = %s", (email,))
        row = cur.fetchone()
    conn.close()
    return row


def create_student(name: str, email: str, stream: str, security_question: str, security_answer: str):
    """Creates a new account. No password — the security Q&A IS the login credential."""
    if find_student_by_email(email):
        raise ValueError("An account with this email already exists.")
    ans_hashed, ans_salt = _hash_answer(security_answer.strip().lower())
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO students
               (name, email, security_question, security_answer_hash, security_answer_salt, stream)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (name, email, security_question, ans_hashed, ans_salt, stream),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()
    return row


def get_security_question(email: str):
    """Returns the security question for an email, or None if no account/question exists."""
    row = find_student_by_email(email)
    if row and row.get("security_question"):
        return row["security_question"]
    return None


def authenticate_with_security(email: str, security_answer: str):
    """Returns the student row if the security answer is correct, else None."""
    row = find_student_by_email(email)
    if row and row.get("security_answer_hash") and _verify_answer(
        security_answer.strip().lower(), row["security_answer_hash"], row["security_answer_salt"]
    ):
        return row
    return None


def get_student_tier(student_id) -> str:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tier, tier_active_until FROM students WHERE id = %s", (student_id,)
        )
        row = cur.fetchone()
    conn.close()
    if not row:
        return "Aura Alpha"
    if row["tier"] != "Aura Alpha" and row["tier_active_until"] and row["tier_active_until"] < date.today():
        return "Aura Alpha"  # subscription lapsed, fall back to free
    return row["tier"]


def upgrade_student_tier(student_id, tier: str, active_until: date):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE students SET tier = %s, tier_active_until = %s WHERE id = %s",
            (tier, active_until, student_id),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------ sessions (keep login across refresh) --
def get_or_create_session_token(student_id) -> str:
    """Returns a durable session token for this student, creating one if needed.
    Storing this in the URL (?session=...) lets a refresh restore login without
    re-entering the security question every time."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT token FROM sessions WHERE student_id = %s LIMIT 1", (student_id,))
        row = cur.fetchone()
        if row:
            conn.close()
            return row["token"]
        token = pysecrets.token_urlsafe(24)
        cur.execute(
            "INSERT INTO sessions (token, student_id) VALUES (%s, %s)",
            (token, student_id),
        )
    conn.commit()
    conn.close()
    return token


def find_student_by_token(token: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.* FROM students s
               JOIN sessions sess ON sess.student_id = s.id
               WHERE sess.token = %s""",
            (token,),
        )
        row = cur.fetchone()
    conn.close()
    return row


# ------------------------------------------------------------ chat memory --
def save_message(student_id, subject, exam_level, role, content):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO chat_history (student_id, subject, exam_level, role, content)
               VALUES (%s, %s, %s, %s, %s)""",
            (student_id, subject, exam_level, role, content),
        )
    conn.commit()
    conn.close()


def load_recent_history(student_id, subject=None, limit=30):
    conn = get_connection()
    with conn.cursor() as cur:
        if subject:
            cur.execute(
                """SELECT role, content FROM chat_history
                   WHERE student_id = %s AND subject = %s ORDER BY created_at DESC LIMIT %s""",
                (student_id, subject, limit),
            )
        else:
            cur.execute(
                """SELECT role, content FROM chat_history
                   WHERE student_id = %s ORDER BY created_at DESC LIMIT %s""",
                (student_id, limit),
            )
        rows = cur.fetchall()
    conn.close()
    return list(reversed(rows))  # oldest first


def clear_chat_history_from(student_id, subject, keep_before_id):
    """Deletes chat_history rows for this student/subject at or after keep_before_id.
    Used when a student edits an earlier message — everything after that point
    (the old answer and anything that followed) is discarded since it's being redone."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM chat_history
               WHERE student_id = %s AND subject = %s AND id >= %s""",
            (student_id, subject, keep_before_id),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------- daily usage caps --
def get_today_usage(student_id) -> int:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT question_count FROM usage_log WHERE student_id = %s AND usage_date = CURRENT_DATE",
            (student_id,),
        )
        row = cur.fetchone()
    conn.close()
    return row["question_count"] if row else 0


def increment_usage(student_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO usage_log (student_id, usage_date, question_count)
               VALUES (%s, CURRENT_DATE, 1)
               ON CONFLICT (student_id, usage_date)
               DO UPDATE SET question_count = usage_log.question_count + 1""",
            (student_id,),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------- payments ----
def create_payment_record(student_id, tx_ref, tier, amount_ngn):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO payments (student_id, tx_ref, tier, amount_ngn, status)
               VALUES (%s, %s, %s, %s, 'pending')""",
            (student_id, tx_ref, tier, amount_ngn),
        )
    conn.commit()
    conn.close()


def mark_payment_status(tx_ref, status, flw_transaction_id=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE payments SET status = %s, flw_transaction_id = COALESCE(%s, flw_transaction_id)
               WHERE tx_ref = %s""",
            (status, flw_transaction_id, tx_ref),
        )
    conn.commit()
    conn.close()


def get_payment(tx_ref):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM payments WHERE tx_ref = %s", (tx_ref,))
        row = cur.fetchone()
    conn.close()
    return row


# ------------------------------------------------------------- admin dashboard stats --
def get_admin_stats():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM students")
        total_students = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM students WHERE created_at::date = CURRENT_DATE")
        signups_today = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM students WHERE tier = 'Aura Alpha+'")
        alpha_plus_subscribers = cur.fetchone()["n"]

        cur.execute("SELECT COALESCE(SUM(amount_ngn), 0) AS total FROM payments WHERE status = 'successful'")
        total_revenue = cur.fetchone()["total"]

        cur.execute(
            """SELECT COUNT(*) AS n FROM chat_history
               WHERE role = 'user' AND created_at::date = CURRENT_DATE"""
        )
        questions_today = cur.fetchone()["n"]

        cur.execute(
            """SELECT COUNT(DISTINCT student_id) AS n FROM chat_history
               WHERE created_at::date = CURRENT_DATE"""
        )
        active_today = cur.fetchone()["n"]

        cur.execute(
            """SELECT name, email, stream, tier, created_at FROM students
               ORDER BY created_at DESC LIMIT 10"""
        )
        recent_signups = cur.fetchall()

        cur.execute(
            """SELECT subject, COUNT(*) AS n FROM chat_history
               WHERE subject IS NOT NULL AND role = 'user'
               GROUP BY subject ORDER BY n DESC LIMIT 10"""
        )
        top_subjects = cur.fetchall()

        cur.execute(
            """SELECT exam_level, COUNT(*) AS n FROM chat_history
               WHERE exam_level IS NOT NULL AND role = 'user'
               GROUP BY exam_level ORDER BY n DESC LIMIT 10"""
        )
        top_exam_levels = cur.fetchall()

    conn.close()
    return {
        "total_students": total_students,
        "signups_today": signups_today,
        "alpha_plus_subscribers": alpha_plus_subscribers,
        "total_revenue": total_revenue,
        "questions_today": questions_today,
        "active_today": active_today,
        "recent_signups": recent_signups,
        "top_subjects": top_subjects,
        "top_exam_levels": top_exam_levels,
    }
