import streamlit as st
import pandas as pd
from openai import OpenAI
import uuid

# ---------- CONFIG ----------
st.set_page_config(page_title="People's Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- PREMIUM UI ----------
st.markdown("""
<style>
html, body, [class*="css"] {
    background: radial-gradient(circle at top, #111827, #020617);
    color: white;
}

/* Glass effect */
.glass {
    background: rgba(255,255,255,0.05);
    border-radius: 16px;
    padding: 15px;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.1);
}

/* Chat bubbles */
.stChatMessage {
    border-radius: 12px;
    padding: 10px;
}

/* Input */
.stChatInput {
    border-radius: 20px;
}
</style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("""
<div class="glass">
    <h1 style='text-align:center;'>⚡ People's Mandate AI</h1>
    <p style='text-align:center;color:gray;'>AI-powered political intelligence</p>
</div>
""", unsafe_allow_html=True)

# ---------- LOAD DATA ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)
sheet_names = list(all_sheets.keys())

# ---------- CHAT MEMORY (MULTI CHAT) ----------
if "chats" not in st.session_state:
    st.session_state.chats = {}

if "current_chat" not in st.session_state:
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = []
    st.session_state.current_chat = chat_id

# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## ⚡ People's Mandate")

    if st.button("➕ New Chat"):
        chat_id = str(uuid.uuid4())
        st.session_state.chats[chat_id] = []
        st.session_state.current_chat = chat_id

    st.markdown("---")

    for chat_id in st.session_state.chats:
        if st.button(f"Chat {list(st.session_state.chats.keys()).index(chat_id)+1}"):
            st.session_state.current_chat = chat_id

# ---------- CURRENT CHAT ----------
messages = st.session_state.chats[st.session_state.current_chat]

# ---------- SHOW CHAT ----------
for msg in messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ---------- INPUT ----------
if prompt := st.chat_input("Ask anything..."):

    messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)

    # ---------- SHEET DESCRIPTION ----------
    sheet_descriptions = ""
    for name, df in all_sheets.items():
        cols = ", ".join(df.columns[:10])
        sheet_descriptions += f"\n{name}: {cols}"

    # ---------- SHEET SELECTION ----------
    sheet_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""
Sheets and columns:
{sheet_descriptions}

Question: {prompt}

Return only best matching sheet name.
"""
            }
        ]
    )

    selected_sheet_raw = sheet_response.choices[0].message.content.strip()

    selected_sheet = next(
        (s for s in sheet_names if s.lower() == selected_sheet_raw.lower()),
        sheet_names[0]
    )

    df = all_sheets[selected_sheet]

    # ---------- DATA CONTEXT (FASTER) ----------
    data_context = df.head(30).to_string(index=False)

    # ---------- MAIN RESPONSE ----------
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are analyzing '{selected_sheet}' data."},
            {"role": "user", "content": f"Data:\n{data_context}\n\nQuestion: {prompt}"}
        ]
    )

    answer = response.choices[0].message.content

    messages.append({"role": "assistant", "content": answer})

    with st.chat_message("assistant"):
        st.write(f"📊 Using Sheet: {selected_sheet}")
        st.write(answer)

        # ---------- CHART ----------
        numeric_df = df.select_dtypes(include="number")

        if not numeric_df.empty:
            st.bar_chart(numeric_df)
