import os
from datetime import date, timedelta

import streamlit as st
from groq import Groq

import config
import db
import payment

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Iris — AI Exam Prep Tutor",
    page_icon="🌺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 2. Custom CSS (kept from your original)
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #0e0e11; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #16161c; border-right: 1px solid #262633; }
    .stTextInput > div > div > input {
        background-color: #1a1a24; color: #ffffff; border: 1px solid #33334d; border-radius: 8px;
    }
    .stButton > button {
        background: linear-gradient(135deg, #b81d24 0%, #800020 100%);
        color: white; border: none; border-radius: 8px; font-weight: 600; transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #d62828 0%, #9e002b 100%);
        box-shadow: 0 4px 12px rgba(184, 29, 36, 0.4);
    }
    [data-testid="stChatMessage"] {
        background-color: #16161f; border: 1px solid #232330; border-radius: 12px;
        padding: 12px; margin-bottom: 10px;
    }
    /* Borderless, minimal dropdowns — like a model picker */
    div[data-testid="stSelectbox"] > div > div {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    div[data-testid="stSelectbox"] > div > div:hover {
        background-color: #1a1a24 !important;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. DB init
# -----------------------------------------------------------------------------
try:
    db.init_schema()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.info("Check that NEON_DATABASE_URL is set in your Render environment.")
    st.stop()

# -----------------------------------------------------------------------------
# 4. Handle Flutterwave redirect BEFORE anything else renders
# -----------------------------------------------------------------------------
query_params = st.query_params
if "transaction_id" in query_params and "tx_ref" in query_params:
    tx_ref = query_params["tx_ref"]
    transaction_id = query_params["transaction_id"]
    verified = payment.verify_payment(transaction_id)
    payment_row = db.get_payment(tx_ref)

    if verified and payment_row and payment_row["status"] != "successful":
        # double-check the amount actually matches what we charged for
        if int(float(verified["amount"])) >= payment_row["amount_ngn"]:
            db.mark_payment_status(tx_ref, "successful", transaction_id)
            active_until = date.today() + timedelta(days=30)
            db.upgrade_student_tier(payment_row["student_id"], payment_row["tier"], active_until)
            st.success(f"Payment confirmed! You're now on {payment_row['tier']} 🎉")
        else:
            db.mark_payment_status(tx_ref, "failed")
            st.error("Payment amount mismatch — please contact support.")
    elif payment_row and payment_row["status"] == "successful":
        st.info("This payment was already confirmed.")
    else:
        db.mark_payment_status(tx_ref, "failed")
        st.error("Payment could not be verified. If you were charged, contact support.")

    st.query_params.clear()

# -----------------------------------------------------------------------------
# 5. Login (creates memory profile)
# -----------------------------------------------------------------------------
SECURITY_QUESTIONS = [
    "What is your favorite subject?",
    "What is the name of your primary school?",
    "What is your best friend's first name?",
    "What city were you born in?",
    "What is your father's first name?",
]

if "student" not in st.session_state:
    st.title("🌺 Iris Tutor Studio")
    st.caption("Targeted exam preparation & concept mastery engine.")

    check_email = st.text_input("Your email", key="check_email").strip().lower()

    if check_email:
        existing_question = db.get_security_question(check_email)

        if existing_question:
            # ---- Returning student: log in with security answer ----
            st.caption(f"Welcome back! Security question: **{existing_question}**")
            with st.form("login"):
                answer = st.text_input("Your answer")
                submitted = st.form_submit_button("Log in")
                if submitted:
                    row = db.authenticate_with_security(check_email, answer)
                    if row:
                        st.session_state.student = row
                        st.rerun()
                    else:
                        st.error("That answer doesn't match. Try again.")
        else:
            # ---- New student: sign up with name + security Q&A ----
            st.caption("New here — let's set up your account.")
            with st.form("signup"):
                name = st.text_input("Your name")
                security_question = st.selectbox("Pick a security question", SECURITY_QUESTIONS)
                security_answer = st.text_input("Your answer")
                stream = st.selectbox("Your stream", list(config.STREAMS.keys()))
                submitted = st.form_submit_button("Create account & start learning")
                if submitted:
                    if not (name and security_answer):
                        st.error("Please enter your name and an answer.")
                    else:
                        st.session_state.student = db.create_student(
                            name.strip(), check_email, stream, security_question, security_answer.strip()
                        )
                        st.rerun()

    st.stop()

student = st.session_state.student
current_tier = db.get_student_tier(student["id"])
tier_info = config.MODEL_TIERS[current_tier]

# -----------------------------------------------------------------------------
# 6. Sidebar — subject, exam level, stream-filtered subjects, tier
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🌺 **Iris Tutor Studio**")
    st.caption(f"Welcome back, {student['name']}")
    st.divider()

    stream = st.selectbox("🧭 Stream", list(config.STREAMS.keys()),
                           index=list(config.STREAMS.keys()).index(student["stream"]) if student["stream"] in config.STREAMS else 0)

    subject = st.selectbox("📚 Select Subject", config.subjects_for_stream(stream))

    exam_target = st.selectbox("🎯 Target Exam / Level", config.EXAM_LEVELS)

    st.divider()
    st.markdown(f"### Current plan: **{current_tier}**")
    st.caption(tier_info["description"])

    if current_tier == config.FREE_TIER_NAME:
        used_today = db.get_today_usage(student["id"])
        limit = tier_info["daily_question_limit"]
        st.progress(min(used_today / limit, 1.0), text=f"{used_today}/{limit} questions today")
        st.caption("Switch to Alpha+ anytime using the dropdown above the chat box.")

    st.divider()
    if st.button("🗑️ Clear chat display", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# -----------------------------------------------------------------------------
# 7. Enforce free-tier daily cap
# -----------------------------------------------------------------------------
if current_tier == config.FREE_TIER_NAME:
    used_today = db.get_today_usage(student["id"])
    if used_today >= tier_info["daily_question_limit"]:
        st.title("🌺 Iris | Exam Prep Tutor")
        st.warning(
            f"You've used all {tier_info['daily_question_limit']} free questions for today. "
            "Come back tomorrow, or upgrade in the sidebar for unlimited access."
        )
        st.stop()

# -----------------------------------------------------------------------------
# 8. Groq client
# -----------------------------------------------------------------------------
groq_api_key = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", "")
if not groq_api_key:
    st.error("🔑 Groq API Key missing! Set `GROQ_API_KEY` in your Render environment.")
    st.stop()
client = Groq(api_key=groq_api_key)

# -----------------------------------------------------------------------------
# 9. System prompt
# -----------------------------------------------------------------------------
IRIS_SYSTEM_PROMPT = f"""
You are Iris, a world-class, dedicated AI Exam Prep Tutor for Nigerian students.
Your goal is to prepare students to achieve top scores in their exams.

CURRENT CONTEXT:
- Stream: {stream}
- Subject: {subject}
- Target Exam: {exam_target}
- Plan: {current_tier}

YOUR TEACHING METHODOLOGY:
1. Active Recall First: After explaining a concept, ask 1 sharp follow-up question to test understanding.
2. Structure & Clarity: Use bullet points, bold key vocabulary, clean markdown.
3. Marking-Scheme Aligned: Emphasize standard definitions, formulas, and keywords examiners award points for.
4. Analogies & Intuition: Explain concepts with real-world analogies before formulas or syntax.
5. Tone: Encouraging, structured, patient, but firm on technical accuracy.
"""

# -----------------------------------------------------------------------------
# 10. Load persistent chat history — resets whenever the student switches subject
# -----------------------------------------------------------------------------
if st.session_state.get("last_subject") != subject:
    st.session_state.last_subject = subject
    past = db.load_recent_history(student["id"], subject=subject)
    if past:
        st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in past]
    else:
        st.session_state.messages = [{
            "role": "assistant",
            "content": f"Hello! I'm **Iris** 🌺. Ready to master **{subject}** for your {exam_target}?\n\nWhat specific topic or question are we tackling today?"
        }]

# -----------------------------------------------------------------------------
# 11. Chat UI
# -----------------------------------------------------------------------------
st.title("🌺 Iris | Exam Prep Tutor")
st.caption(f"Active Session: **{subject}** | Exam: **{exam_target}** | Plan: **{current_tier}**")

for msg in st.session_state.messages:
    avatar = "🌺" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---- Inline model badge/picker, sits just above the input like a model selector ----
active_model = tier_info["model"]
active_label = current_tier.replace("Iris ", "")
premium_used_today = db.get_today_usage(student["id"])
has_alpha_plus = current_tier == "Iris Alpha+"
remaining = 0

if has_alpha_plus:
    premium_limit = tier_info["premium_daily_limit"]
    remaining = max(premium_limit - premium_used_today, 0)

alpha_plus_label = f"🌸 Alpha+ · full model ({remaining} left today)" if has_alpha_plus and remaining > 0 else "🌸 Alpha+ · unlock full model"

picker_col, _ = st.columns([2, 3])
with picker_col:
    choice = st.selectbox(
        "Model", ["🌸 Alpha · fast & free", alpha_plus_label],
        label_visibility="collapsed",
    )

if choice.startswith("🌸 Alpha+"):
    if has_alpha_plus and remaining > 0:
        active_model = config.MODEL_TIERS["Iris Alpha+"]["model"]
        active_label = "Alpha+"
    elif has_alpha_plus and remaining == 0:
        st.caption("Out of full-model requests today — running on Alpha until tomorrow.")
        active_model = config.MODEL_TIERS["Iris Alpha"]["model"]
        active_label = "Alpha (Alpha+ daily limit reached)"
    else:
        # Not subscribed yet — send them straight to payment
        st.info("Alpha+ is ₦500 — unlocks the full-power model for 9 requests/day.")
        if st.button("Unlock Alpha+ — ₦500", use_container_width=True):
            try:
                redirect_url = os.getenv("APP_BASE_URL", "https://iris-tutor.onrender.com")
                tinfo = config.MODEL_TIERS["Iris Alpha+"]
                tx_ref, link = payment.initiate_payment(
                    student_email=student["email"],
                    student_name=student["name"],
                    tier="Iris Alpha+",
                    amount_ngn=tinfo["price_ngn"],
                    redirect_url=redirect_url,
                )
                db.create_payment_record(student["id"], tx_ref, "Iris Alpha+", tinfo["price_ngn"])
                st.link_button("Click to complete payment →", link, use_container_width=True)
            except Exception as e:
                st.error(f"Could not start payment: {e}")
        active_model = config.MODEL_TIERS["Iris Alpha"]["model"]
        active_label = "Alpha"
else:
    active_model = config.MODEL_TIERS["Iris Alpha"]["model"]
    active_label = "Alpha"

active_max_tokens = (
    config.MODEL_TIERS["Iris Alpha+"]["max_tokens"]
    if active_model == config.MODEL_TIERS["Iris Alpha+"]["model"]
    else config.MODEL_TIERS["Iris Alpha"]["max_tokens"]
)

if user_input := st.chat_input("Ask a question, request a practice drill, or paste a problem..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    db.save_message(student["id"], subject, exam_target, "user", user_input)
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    api_messages = [{"role": "system", "content": IRIS_SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]

    with st.chat_message("assistant", avatar="🌺"):
        response_placeholder = st.empty()
        full_response = ""
        try:
            completion = client.chat.completions.create(
                model=active_model,
                messages=api_messages,
                temperature=0.5,
                max_tokens=active_max_tokens,
                stream=True,
            )
            for chunk in completion:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)
        except Exception as e:
            st.error(f"Error calling Groq API: {str(e)}")

    if full_response:
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        db.save_message(student["id"], subject, exam_target, "assistant", full_response)
        # Track usage: free tier counts toward its daily cap, Alpha+ counts toward its
        # full-model daily allowance (only when the full model was actually used)
        if current_tier == config.FREE_TIER_NAME:
            db.increment_usage(student["id"])
        elif current_tier == "Iris Alpha+" and active_model == config.MODEL_TIERS["Iris Alpha+"]["model"]:
            db.increment_usage(student["id"])
