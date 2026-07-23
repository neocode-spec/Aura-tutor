import os
import streamlit as st
from groq import Groq

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Iris — AI Exam Prep Tutor",
    page_icon="🌺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. Custom CSS Styling (Dark Theme & Smooth UI)
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    /* Dark Theme Background */
    .stApp {
        background-color: #0e0e11;
        color: #e0e0e0;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #16161c;
        border-right: 1px solid #262633;
    }

    /* Custom Input Box styling */
    .stTextInput > div > div > input {
        background-color: #1a1a24;
        color: #ffffff;
        border: 1px solid #33334d;
        border-radius: 8px;
    }

    /* Primary Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #b81d24 0%, #800020 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #d62828 0%, #9e002b 100%);
        box-shadow: 0 4px 12px rgba(184, 29, 36, 0.4);
    }

    /* Chat Containers */
    [data-testid="stChatMessage"] {
        background-color: #16161f;
        border: 1px solid #232330;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. API Initialization
# -----------------------------------------------------------------------------
# Fetch Groq API Key from environment variable or Streamlit Secrets
groq_api_key = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", "")

if not groq_api_key:
    st.error("🔑 Groq API Key missing! Please set `GROQ_API_KEY` in your environment or Render settings.")
    st.stop()

client = Groq(api_key=groq_api_key)

# -----------------------------------------------------------------------------
# 4. Sidebar Controls & Customization
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🌺 **Iris Tutor Studio**")
    st.caption("Targeted exam preparation & concept mastery engine.")
    st.divider()

    # Student Context Setup
    subject = st.selectbox(
        "📚 Select Subject",
        ["Computer Science", "Data Analytics", "Mathematics", "Physics", "Chemistry", "Biology", "General Studies"]
    )
    
    exam_target = st.text_input("🎯 Target Exam / Level", placeholder="e.g., University Finals, WAEC, SAT")
    
    teaching_style = st.select_slider(
        "🎛️ Tutoring Rigor",
        options=["Beginner Friendly", "Standard Exam Prep", "Hardcore Drill"],
        value="Standard Exam Prep"
    )

    st.divider()

    if st.button("🗑️ Reset Session", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# -----------------------------------------------------------------------------
# 5. System Prompt Definition (Iris Persona)
# -----------------------------------------------------------------------------
IRIS_SYSTEM_PROMPT = f"""
You are Iris, a world-class, dedicated AI Exam Prep Tutor. 
Your goal is to prepare students to achieve top scores in their exams.

CURRENT CONTEXT:
- Subject: {subject}
- Target Exam: {exam_target if exam_target else "General Academic Assessment"}
- Tutoring Rigor: {teaching_style}

YOUR TEACHING METHODOLOGY:
1. Active Recall First: Don't just lecture or dump text. After explaining a concept, ask 1 sharp follow-up question to test if the student truly understands.
2. Structure & Clarity: Use bullet points, bold key technical vocabulary, and clean markdown layout for scannability.
3. Marking-Scheme Aligned: Emphasize standard definitions, formulas, and critical keywords that examiners award points for.
4. Analogies & Intuition: Explain complex theoretical concepts with simple, real-world analogies before diving into academic formulas or syntax.
5. Tone: Encouraging, structured, patient, but firm on technical accuracy. Never give sloppy or vague answers.
"""

# -----------------------------------------------------------------------------
# 6. Session State for Chat
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"Hello! I'm **Iris** 🌺. Ready to master **{subject}** for your {exam_target if exam_target else 'upcoming exams'}?\n\nWhat specific topic or question are we tackling today?"
        }
    ]

# -----------------------------------------------------------------------------
# 7. Chat Interface & Rendering
# -----------------------------------------------------------------------------
st.title("🌺 Iris | Exam Prep Tutor")
st.caption(f"Active Session: **{subject}** | Rigor Mode: **{teaching_style}**")

# Render previous messages
for msg in st.session_state.messages:
    avatar = "🌺" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# User prompt input
if user_input := st.chat_input("Ask a question, request a practice drill, or paste a problem..."):
    # Store and display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    # Format messages for Groq API
    api_messages = [{"role": "system", "content": IRIS_SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]

    # Generate assistant streaming response
    with st.chat_message("assistant", avatar="🌺"):
        response_placeholder = st.empty()
        full_response = ""

        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
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

    # Store assistant response in session
    if full_response:
        st.session_state.messages.append({"role": "assistant", "content": full_response})
