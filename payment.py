"""
payment.py — Flutterwave Standard Checkout (v3 API) for Iris tier upgrades

Set these in your environment / Render settings:
    FLW_PUBLIC_KEY=FLWPUBK_TEST-xxxx   (safe to expose client-side)
    FLW_SECRET_KEY=FLWSECK_TEST-xxxx   (NEVER expose this one — server only)

v3 remains Flutterwave's stable production API as of 2026; v4 (OAuth-based)
exists in beta — migrate later if you want, but v3 works fine for this.
"""

import os
import uuid
import requests
import streamlit as st

FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY") or st.secrets.get("FLW_SECRET_KEY", "")
FLW_BASE_URL = "https://api.flutterwave.com/v3"


def initiate_payment(student_email: str, student_name: str, tier: str, amount_ngn: int, redirect_url: str):
    """
    Creates a Flutterwave Standard Checkout link.
    Returns (tx_ref, payment_link) or raises an exception on failure.
    """
    tx_ref = f"iris-{uuid.uuid4().hex[:12]}"

    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount_ngn),
        "currency": "NGN",
        "redirect_url": redirect_url,
        "customer": {
            "email": student_email,
            "name": student_name,
        },
        "customizations": {
            "title": "Iris Tutor",
            "description": f"Upgrade to {tier}",
        },
    }

    resp = requests.post(
        f"{FLW_BASE_URL}/payments",
        json=payload,
        headers={
            "Authorization": f"Bearer {FLW_SECRET_KEY}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    data = resp.json()

    if data.get("status") != "success":
        raise RuntimeError(f"Flutterwave error: {data.get('message', 'unknown error')}")

    return tx_ref, data["data"]["link"]


def verify_payment(transaction_id: str):
    """
    Confirms a transaction actually succeeded. ALWAYS call this before
    upgrading a student's tier — never trust the redirect alone, since
    a user can forge the URL params.
    Returns the transaction data dict, or None if verification failed.
    """
    resp = requests.get(
        f"{FLW_BASE_URL}/transactions/{transaction_id}/verify",
        headers={"Authorization": f"Bearer {FLW_SECRET_KEY}"},
        timeout=15,
    )
    data = resp.json()

    if (
        data.get("status") == "success"
        and data["data"]["status"] == "successful"
    ):
        return data["data"]
    return None
