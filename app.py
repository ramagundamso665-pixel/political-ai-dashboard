import streamlit as st
from openai import OpenAI
import uuid

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- UI STYLE ----------
st.markdown("""
<style>
html, body, [class*="css"] {
    background: radial-gradient(circle at top, #111827, #020617);
    color: white;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #020617;
    border-right: 1px solid rgba(255,255,255,0.08);
}

/* Glass cards */
.glass {
    background: rgba(255,255,255,0.05);
    border-radius: 18px;
    padding: 16px;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.1);
}

/* Title */
.title {
    font-size: 34px;
    font-weight: 700;
}

/* Subtitle */
.subtitle {
    color: #9ca3af;
    font-size: 14px;
}

/* Chat input */
.stChatInput {
    border-radius: 25px;
}

/* Chat bubbles */
.stChatMessage {
    border-radius: 14px;
    padding: 10px;
}

/* Buttons */
.stButton button {
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ---------- SESSION ----------
if "chats" not in st.session_state:
    st.session_state.chats = {}

if "current_chat" not in st.session_state:
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = []
    st.session_state.current_chat = chat_id

# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## ⚡ Mandate AI")

    if st.button("➕ New Chat"):
        chat_id = str(uuid.uuid4())
        st.session_state.chats[chat_id] = []
        st.session_state.current_chat = chat_id

    st.markdown("---")

    # Show chat history
    for chat_id in st.session_state.chats:
        if st.button(f"Chat {list(st.session_state.chats.keys()).index(chat_id)+1}"):
            st.session_state.current_chat = chat_id

# ---------- HEADER ----------
st.markdown("""
<div class="glass">
    <div class="title">⚡ Mandate AI</div>
    <div class="subtitle">AI-powered political intelligence</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------- CHAT ----------
messages = st.session_state.chats[st.session_state.current_chat]

for msg in messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask about politics, governance, trends...")

if prompt:
    messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        with st.spinner("Analyzing..."):
            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response)

    messages.append({"role": "assistant", "content": full_response})
