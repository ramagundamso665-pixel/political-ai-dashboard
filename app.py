import streamlit as st
import pandas as pd
from openai import OpenAI
import uuid
import json
import os

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(layout="wide")

# ---------- SAVE / LOAD ----------
CHAT_FILE = "chat_store.json"

def load_chats():
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_chats(chats):
    with open(CHAT_FILE, "w") as f:
        json.dump(chats, f)

# ---------- SESSION ----------
if "chats" not in st.session_state:
    st.session_state.chats = load_chats()

if "chat_names" not in st.session_state:
    st.session_state.chat_names = {}

if "current_chat" not in st.session_state:
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = []
    st.session_state.current_chat = chat_id

# ---------- UI ----------
st.markdown("""
<style>
html, body, [class*="css"] {
    background: radial-gradient(circle at top, #111827, #020617);
    color: white;
}
.glass {
    background: rgba(255,255,255,0.05);
    border-radius: 16px;
    padding: 15px;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.1);
}
.stChatMessage {
    border-radius: 10px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="glass">
<h1 style='text-align:center;'>🤖 AI Political Assistant</h1>
</div>
""", unsafe_allow_html=True)

# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## Chats")

    if st.button("➕ New Chat"):
        chat_id = str(uuid.uuid4())
        st.session_state.chats[chat_id] = []
        st.session_state.current_chat = chat_id

    st.markdown("---")

    for chat_id in st.session_state.chats:
        name = st.session_state.chat_names.get(chat_id, "New Chat")
        if st.button(name):
            st.session_state.current_chat = chat_id

# ---------- LOAD DATA ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)
sheet_names = list(all_sheets.keys())

# ---------- CHAT ----------
messages = st.session_state.chats[st.session_state.current_chat]

for msg in messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ---------- INPUT ----------
if prompt := st.chat_input("Ask anything..."):

    messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)

    # Auto chat name (first message)
    if st.session_state.current_chat not in st.session_state.chat_names:
        st.session_state.chat_names[st.session_state.current_chat] = prompt[:30]

    # ---------- YOUR ORIGINAL LOGIC ----------
    sheet_descriptions = ""

    for name, df in all_sheets.items():
        cols = ", ".join(df.columns[:10])
        sheet_descriptions += f"\n{name}: {cols}"

    sheet_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""
You are a data expert.

Below are sheets with their column names:
{sheet_descriptions}

User question: {prompt}

Choose the MOST relevant sheet.
Return ONLY the sheet name exactly.
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

    data_context = df.head(50).to_string(index=False)

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

        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            st.bar_chart(numeric_df)

# ---------- SAVE ----------
save_chats(st.session_state.chats)
