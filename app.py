import streamlit as st
from openai import OpenAI

# ---------- CONFIG ----------
col1, col2 = st.columns([1,5])

with col1:
    st.markdown("## ⚡")

with col2:
    st.markdown("## Mandate AI")
    st.caption("AI-powered political intelligence")

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
