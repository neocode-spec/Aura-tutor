import os
import re
from datetime import date, timedelta

import streamlit as st
from groq import Groq
from PIL import Image

import config
import db
import payment

FLAME_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "flame_icon.png")
try:
    _page_icon = Image.open(FLAME_ICON_PATH)
except Exception:
    _page_icon = "🔥"  # fallback if the asset didn't make it into the deploy

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Aura — AI Exam Prep Tutor",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 2. Custom CSS — blue/purple gradient brand
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #0e0e11; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #16161c; border-right: 1px solid #262633; }
    .stTextInput > div > div > input {
        background-color: #1a1a24; color: #ffffff; border: 1px solid #33334d; border-radius: 8px;
    }
    .stButton > button {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: white; border: none; border-radius: 8px; font-weight: 600; transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        box-shadow: 0 4px 12px rgba(124, 58, 237, 0.4);
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
# 3b. Admin dashboard — visit yourURL?admin=1, password-gated
# -----------------------------------------------------------------------------
if st.query_params.get("admin") == "1":
    st.title("🔥 Aura — Admin Dashboard")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    entered = st.text_input("Admin password", type="password")
    if not admin_password:
        st.error("ADMIN_PASSWORD is not set in your Render environment yet — set it to use this page.")
        st.stop()
    if entered != admin_password:
        if entered:
            st.error("Wrong password.")
        st.stop()

    stats = db.get_admin_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total students", stats["total_students"])
    c2.metric("Signups today", stats["signups_today"])
    c3.metric("Active today", stats["active_today"])
    c4, c5, c6 = st.columns(3)
    c4.metric("Alpha+ subscribers", stats["alpha_plus_subscribers"])
    c5.metric("Revenue (₦, all-time)", f"₦{stats['total_revenue']:,}")
    c6.metric("Questions asked today", stats["questions_today"])

    st.divider()
    st.subheader("Most recent signups")
    for s in stats["recent_signups"]:
        st.caption(f"**{s['name']}** ({s['email']}) — {s['stream']} — {s['tier']} — {s['created_at']:%Y-%m-%d %H:%M}")

    st.divider()
    col_subj, col_exam = st.columns(2)
    with col_subj:
        st.subheader("Most-asked subjects")
        if stats["top_subjects"]:
            for row in stats["top_subjects"]:
                st.caption(f"**{row['subject']}** — {row['n']} questions")
        else:
            st.caption("No questions logged yet.")
    with col_exam:
        st.subheader("Most common exam targets")
        if stats["top_exam_levels"]:
            for row in stats["top_exam_levels"]:
                st.caption(f"**{row['exam_level']}** — {row['n']} questions")
        else:
            st.caption("No questions logged yet.")

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
    st.title("🔥 Aura Tutor Studio")
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
    logo_col, title_col = st.columns([1, 4])
    with logo_col:
        st.image(FLAME_ICON_PATH, width=40)
    with title_col:
        st.markdown("## **Aura Tutor Studio**")
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
        st.title("🔥 Aura | Exam Prep Tutor")
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
AURA_SYSTEM_PROMPT = f"""
You are Aura, a world-class, dedicated AI Exam Prep Tutor for Nigerian students.
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

MATH FORMATTING — FOLLOW EXACTLY, THIS IS STRICT:
- Every formula or equation MUST be wrapped in LaTeX dollar-sign delimiters, nothing else.
- Inline formula (within a sentence): wrap it in single dollar signs, e.g. $F = ma$
- Standalone/block formula (on its own line): wrap it in double dollar signs, e.g. $$KE = \\tfrac{{1}}{{2}}mv^2$$
- NEVER wrap formulas in plain parentheses like (\\displaystyle ...) — that does not render and shows up as broken text.
- NEVER use \\[ \\] or \\( \\) delimiters — only $ and $$.
- In tables, formulas still need $ delimiters around them, e.g. a table cell should contain $s = ut + \\tfrac{{1}}{{2}}at^2$, not the raw LaTeX with no dollar signs.
"""


def fix_math_formatting(text: str) -> str:
    """
    Safety net — models sometimes ignore the $ instruction and output
    \\( \\), \\[ \\], or (\\displaystyle ...) anyway. Convert those to
    proper $ / $$ delimiters so Streamlit actually renders the math.
    """
    text = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
    text = re.sub(r"\\\((.+?)\\\)", r"$\1$", text, flags=re.DOTALL)
    text = re.sub(r"\(\\displaystyle\s+(.+?)\)", r"$\1$", text)
    return text

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
            "content": f"Hello! I'm **Aura** 🔥. Ready to master **{subject}** for your {exam_target}?\n\nWhat specific topic or question are we tackling today?"
        }]

# -----------------------------------------------------------------------------
# 11. Chat UI
# -----------------------------------------------------------------------------
st.title("🔥 Aura | Exam Prep Tutor")
st.caption(f"Active Session: **{subject}** | Exam: **{exam_target}** | Plan: **{current_tier}**")

if "editing_index" not in st.session_state:
    st.session_state.editing_index = None

for i, msg in enumerate(st.session_state.messages):
    avatar = FLAME_ICON_PATH if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        display_content = fix_math_formatting(msg["content"]) if msg["role"] == "assistant" else msg["content"]
        st.markdown(display_content)
        if msg["role"] == "user":
            btn_col1, btn_col2, _ = st.columns([1, 1, 6])
            with btn_col1:
                if st.button("✏️ Edit", key=f"edit_{i}"):
                    st.session_state.editing_index = i
                    st.rerun()
            with btn_col2:
                # Copy runs entirely client-side (no rerun) via clipboard JS
                safe_text = msg["content"].replace("`", "\\`").replace("</script>", "")
                st.markdown(
                    f"""<button onclick="navigator.clipboard.writeText(`{safe_text}`)"
                        style="background:transparent;border:none;color:#8b5cf6;cursor:pointer;font-size:0.85em;">
                        📋 Copy</button>""",
                    unsafe_allow_html=True,
                )

# ---- Inline model badge/picker, sits just above the input like a model selector ----
active_model = tier_info["model"]
active_label = current_tier.replace("Aura ", "")
premium_used_today = db.get_today_usage(student["id"])
has_alpha_plus = current_tier == "Aura Alpha+"
remaining = 0

if has_alpha_plus:
    premium_limit = tier_info["premium_daily_limit"]
    remaining = max(premium_limit - premium_used_today, 0)

alpha_plus_label = f"🔥 Alpha+ · full model ({remaining} left today)" if has_alpha_plus and remaining > 0 else "🔥 Alpha+ · unlock full model"

picker_col, _ = st.columns([2, 3])
with picker_col:
    choice = st.selectbox(
        "Model", ["🔥 Alpha · fast & free", alpha_plus_label],
        label_visibility="collapsed",
    )

if choice.startswith("🔥 Alpha+"):
    if has_alpha_plus and remaining > 0:
        active_model = config.MODEL_TIERS["Aura Alpha+"]["model"]
        active_label = "Alpha+"
    elif has_alpha_plus and remaining == 0:
        st.caption("Out of full-model requests today — running on Alpha until tomorrow.")
        active_model = config.MODEL_TIERS["Aura Alpha"]["model"]
        active_label = "Alpha (Alpha+ daily limit reached)"
    else:
        # Not subscribed yet — send them straight to payment
        st.info("Alpha+ is ₦500 — unlocks the full-power model for 9 requests/day.")
        if st.button("Unlock Alpha+ — ₦500", use_container_width=True):
            try:
                redirect_url = os.getenv("APP_BASE_URL", "https://iris-tutor.onrender.com")
                tinfo = config.MODEL_TIERS["Aura Alpha+"]
                tx_ref, link = payment.initiate_payment(
                    student_email=student["email"],
                    student_name=student["name"],
                    tier="Aura Alpha+",
                    amount_ngn=tinfo["price_ngn"],
                    redirect_url=redirect_url,
                )
                db.create_payment_record(student["id"], tx_ref, "Aura Alpha+", tinfo["price_ngn"])
                st.link_button("Click to complete payment →", link, use_container_width=True)
            except Exception as e:
                st.error(f"Could not start payment: {e}")
        active_model = config.MODEL_TIERS["Aura Alpha"]["model"]
        active_label = "Alpha"
else:
    active_model = config.MODEL_TIERS["Aura Alpha"]["model"]
    active_label = "Alpha"

active_max_tokens = (
    config.MODEL_TIERS["Aura Alpha+"]["max_tokens"]
    if active_model == config.MODEL_TIERS["Aura Alpha+"]["model"]
    else config.MODEL_TIERS["Aura Alpha"]["max_tokens"]
)

def send_and_respond(text: str):
    """Sends a user message, streams Aura's reply, saves both, tracks usage."""
    st.session_state.messages.append({"role": "user", "content": text})
    db.save_message(student["id"], subject, exam_target, "user", text)
    with st.chat_message("user", avatar="👤"):
        st.markdown(text)

    api_messages = [{"role": "system", "content": AURA_SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]

    full_response = ""
    with st.chat_message("assistant", avatar=FLAME_ICON_PATH):
        response_placeholder = st.empty()
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
                response_placeholder.markdown(fix_math_formatting(full_response) + "▌")
            full_response = fix_math_formatting(full_response)
            response_placeholder.markdown(full_response)
        except Exception as e:
            st.error(f"Error calling Groq API: {str(e)}")

    if full_response:
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        db.save_message(student["id"], subject, exam_target, "assistant", full_response)
        if current_tier == config.FREE_TIER_NAME:
            db.increment_usage(student["id"])
        elif current_tier == "Aura Alpha+" and active_model == config.MODEL_TIERS["Aura Alpha+"]["model"]:
            db.increment_usage(student["id"])


# ---- Handle an in-progress edit (resubmit truncates history from that point) ----
if st.session_state.get("editing_index") is not None:
    idx = st.session_state.editing_index
    with st.form("edit_form"):
        edited_text = st.text_area("Edit your message", value=st.session_state.messages[idx]["content"])
        col_a, col_b = st.columns(2)
        resubmit = col_a.form_submit_button("Resubmit", use_container_width=True)
        cancel = col_b.form_submit_button("Cancel", use_container_width=True)
    if resubmit:
        st.session_state.messages = st.session_state.messages[:idx]
        st.session_state.editing_index = None
        send_and_respond(edited_text)
        st.rerun()
    if cancel:
        st.session_state.editing_index = None
        st.rerun()

if user_input := st.chat_input("Ask a question, request a practice drill, or paste a problem..."):
    send_and_respond(user_input)
