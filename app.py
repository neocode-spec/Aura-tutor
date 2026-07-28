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
# 2. Custom CSS
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
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. DB Init
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
# 5. Session & Auto-Login Persistence
# -----------------------------------------------------------------------------
if "student" not in st.session_state:
    st.title("🌺 Iris Tutor Studio")
    st.caption("Targeted exam preparation & concept mastery engine.")

    with st.form("login"):
        name = st.text_input("Your name")
        email = st.text_input("Your email")
        stream = st.selectbox("Your stream", list(config.STREAMS.keys()))
        submitted = st.form_submit_button("Start learning")
        if submitted:
            if not (name and email):
                st.error("Please enter your name and email.")
            else:
                student_record = db.find_or_create_student(name.strip(), email.strip().lower(), stream)
                st.session_state.student = student_record
                st.rerun()

    st.caption("Already used Iris before? Just enter the same email — your history comes right back.")
    st.stop()

student = st.session_state.student

# Safe Tier Retrieval
current_tier = db.get_student_tier(student["id"])
free_tier_name = getattr(config, "FREE_TIER_NAME", "Alpha")

default_tier_info = {
    "model": "llama-3.1-8b-instant",
    "daily_question_limit": 9,
    "price_ngn": 0,
    "description": "Base tier: 9 free questions per day."
}

if hasattr(config, "MODEL_TIERS"):
    tier_info = config.MODEL_TIERS.get(current_tier, config.MODEL_TIERS.get("Alpha", default_tier_info))
else:
    tier_info = default_tier_info

# -----------------------------------------------------------------------------
# 6. Sidebar — Stream, Subject, Exam Level, Tier & Upgrade
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🌺 **Iris Tutor Studio**")
    st.caption(f"Welcome back, {student['name']}")
    st.divider()

    stream = st.selectbox(
        "🧭 Stream", 
        list(config.STREAMS.keys()),
        index=list(config.STREAMS.keys()).index(student["stream"]) if student["stream"] in config.STREAMS else 0
    )

    subject = st.selectbox("📚 Select Subject", config.subjects_for_stream(stream))
    exam_target = st.selectbox("🎯 Target Exam / Level", config.EXAM_LEVELS)

    st.divider()

    st.markdown(f"### Active Plan: **Iris {current_tier}**")
    st.caption(tier_info.get("description", ""))

    if current_tier == free_tier_name:
        used_today = db.get_today_usage(student["id"])
        limit = tier_info.get("daily_question_limit", 9)
        st.progress(min(used_today / limit, 1.0), text=f"{used_today}/{limit} questions today")

        st.markdown("#### Upgrade Tier")
        alpha_plus_price = 500
        if hasattr(config, "MODEL_TIERS") and "Alpha+" in config.MODEL_TIERS:
            alpha_plus_price = config.MODEL_TIERS["Alpha+"].get("price_ngn", 500)

        if st.button(f"Upgrade to Alpha+ — ₦{alpha_plus_price}/mo", use_container_width=True, key="upgrade_Alpha_plus"):
            try:
                redirect_url = os.getenv("APP_BASE_URL", "https://iris-tutor.onrender.com")
                tx_ref, link = payment.initiate_payment(
                    student_email=student["email"],
                    student_name=student["name"],
                    tier="Alpha+",
                    amount_ngn=alpha_plus_price,
                    redirect_url=redirect_url,
                )
                db.create_payment_record(student["id"], tx_ref, "Alpha+", alpha_plus_price)
                st.link_button("Click to complete payment →", link, use_container_width=True)
            except Exception as e:
                st.error(f"Could not start payment: {e}")

    st.divider()
    if st.button("🗑️ Clear chat display", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# -----------------------------------------------------------------------------
# 7. Enforce free-tier daily cap
# -----------------------------------------------------------------------------
if current_tier == free_tier_name:
    used_today = db.get_today_usage(student["id"])
    limit = tier_info.get("daily_question_limit", 9)
    if used_today >= limit:
        st.title("🌺 Iris | Exam Prep Tutor")
        st.warning(
            f"You've used all {limit} free questions for today on Alpha. "
            "Come back tomorrow, or upgrade to Alpha+ in the sidebar for full model access."
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
# 9. Main Chat Interface Header & Inline Model Dropdown
# -----------------------------------------------------------------------------
st.title("🌺 Iris | Exam Prep Tutor")

col1, col2 = st.columns([3, 1])
with col1:
    st.caption(f"Active Session: **{subject}** | Exam: **{exam_target}**")

with col2:
    model_options = {
        "Alpha 🔽": "Alpha",
        "Alpha+ 🔽": "Alpha+"
    }
    selected_label = st.selectbox(
        "Model",
        options=list(model_options.keys()),
        index=0 if current_tier == "Alpha" else 1,
        label_visibility="collapsed"
    )
    selected_model_tier = model_options[selected_label]

# -----------------------------------------------------------------------------
# 10. System prompt
# -----------------------------------------------------------------------------
IRIS_SYSTEM_PROMPT = f"""
You are Iris, a world-class, dedicated AI Exam Prep Tutor for Nigerian students.
Your goal is to prepare students to achieve top scores in their exams.

CURRENT CONTEXT:
- Stream: {stream}
- Subject: {subject}
- Target Exam: {exam_target}
- Plan: {current_tier}
- Engine: {selected_model_tier}

YOUR TEACHING METHODOLOGY:
1. Active Recall First: After explaining a concept, ask 1 sharp follow-up question to test understanding.
2. Structure & Clarity: Use bullet points, bold key vocabulary, clean markdown.
3. Marking-Scheme Aligned: Emphasize standard definitions, formulas, and keywords examiners award points for.
4. Analogies & Intuition: Explain concepts with real-world analogies before formulas or syntax.
5. Tone: Encouraging, structured, patient, but firm on technical accuracy.
"""

# -----------------------------------------------------------------------------
# 11. Load persistent chat history from Neon
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    past = db.load_recent_history(student["id"])
    if past:
        st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in past]
    else:
        st.session_state.messages = [{
            "role": "assistant",
            "content": f"Hello! I'm **Iris** 🌺. Ready to master **{subject}** for your {exam_target}?\n\nWhat specific topic or question are we tackling today?"
        }]

# -----------------------------------------------------------------------------
# 12. Chat UI & Message Loop
# -----------------------------------------------------------------------------
for msg in st.session_state.messages:
    avatar = "🌺" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if user_input := st.chat_input("Ask a question, request a practice drill, or paste a problem..."):
    if selected_model_tier == "Alpha+" and current_tier == free_tier_name:
        st.warning("The Alpha+ model requires a full model subscription (₦500/mo). Please upgrade in the sidebar to use this model.")
        st.stop()

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
        
        model_id = "llama-3.1-8b-instant" if selected_model_tier == "Alpha" else "llama-3.3-70b-versatile"

        try:
            completion = client.chat.completions.create(
                model=model_id,
                messages=api_messages,
                temperature=0.5,
                max_tokens=2048,
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
        if current_tier == free_tier_name:
            db.increment_usage(student["id"])
