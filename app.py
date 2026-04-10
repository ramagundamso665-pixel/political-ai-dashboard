import streamlit as st
from openai import OpenAI
import streamlit as st
from openai import OpenAI
st.markdown("""
<style>
html, body, [class*="css"] {
    background-color: #0b0f19;
    color: white;
}

.block-container {
    padding-top: 2rem;
    max-width: 900px;
}

h1 {
    font-size: 42px !important;
    font-weight: 700;
    text-align: center;
}

p {
    text-align: center;
    color: #9ca3af;
}

.stChatInput {
    border-radius: 20px;
}

.stChatMessage {
    border-radius: 12px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)

# rest of your code continues...
# ---------- CONFIG ----------
col1, col2 = st.columns([1,5])

st.markdown("""
<h1>⚡ Mandate AI</h1>
<p>AI-powered political intelligence</p>
""", unsafe_allow_html=True)
st.markdown("---")

# ---------- API ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- MEMORY ----------
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------- SHOW CHAT ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------- INPUT ----------
prompt = st.chat_input("Type your message...")

if prompt:
    # user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # assistant response
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
