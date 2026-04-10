import streamlit as st
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- UI STYLE ----------
st.markdown("""
<style>

/* Background */
html, body, [class*="css"] {
    background: linear-gradient(135deg, #0b0f19, #111827);
    color: white;
}

/* Main container */
.block-container {
    max-width: 1100px;
    padding-top: 1.5rem;
}

/* Glass effect */
.glass {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 15px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.1);
}

/* Title */
.title {
    font-size: 36px;
    font-weight: 700;
}

/* Subtitle */
.subtitle {
    color: #9ca3af;
    font-size: 14px;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0b0f19;
    border-right: 1px solid rgba(255,255,255,0.1);
}

/* Chat input */
.stChatInput {
    border-radius: 20px;
}

/* Chat bubbles */
.stChatMessage {
    border-radius: 12px;
    padding: 10px;
}

</style>
""", unsafe_allow_html=True)

# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## ⚡ Mandate AI")
    st.markdown("### Chats")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if st.button("➕ New Chat"):
        st.session_state.messages = []

# ---------- HEADER ----------
st.markdown("""
<div class="glass">
    <div class="title">⚡ Mandate AI</div>
    <div class="subtitle">AI-powered political intelligence</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------- CHAT ----------
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
prompt = st.chat_input("Ask about politics, governance, insights...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        with st.spinner("Thinking..."):
            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=st.session_state.messages,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response)

    st.session_state.messages.append(
        {"role": "assistant", "content": full_response}
    )
