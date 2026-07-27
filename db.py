"""
db.py — Neon Postgres connection, schema, and memory helpers for Iris

Set NEON_DATABASE_URL in your environment or Render settings:
    postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require
"""

import os
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date

NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL") or st.secrets.get("NEON_DATABASE_URL", "")


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
        stream TEXT,
        tier TEXT DEFAULT 'Iris Alpha',
        tier_active_until DATE,
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
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- students --
def get_or_create_student(name: str, email: str, stream: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM students WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            conn.close()
            return row
        cur.execute(
            "INSERT INTO students (name, email, stream) VALUES (%s, %s, %s) RETURNING *",
            (name, email, stream),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()
    return row


def get_student_tier(student_id) -> str:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tier, tier_active_until FROM students WHERE id = %s", (student_id,)
        )
        row = cur.fetchone()
    conn.close()
    if not row:
        return "Iris Alpha"
    if row["tier"] != "Iris Alpha" and row["tier_active_until"] and row["tier_active_until"] < date.today():
        return "Iris Alpha"  # subscription lapsed, fall back to free
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


def load_recent_history(student_id, limit=30):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT role, content FROM chat_history
               WHERE student_id = %s ORDER BY created_at DESC LIMIT %s""",
            (student_id, limit),
        )
        rows = cur.fetchall()
    conn.close()
    return list(reversed(rows))  # oldest first


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
