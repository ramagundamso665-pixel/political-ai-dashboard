import streamlit as st
import pandas as pd
from openai import OpenAI
import uuid
import json
import os

# ---------- CONFIG ----------
st.set_page_config(page_title="People's Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
CHAT_FILE = "chat_store.json"

# ---------- SAFE LOAD ----------
def load_chats():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

# ---------- SAVE ----------
def save_chats(chats):
    with open(CHAT_FILE, "w") as f:
        json.dump(chats, f, indent=2)

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
html, body {
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
button {
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("""
<div class="glass">
<h1 style='text-align:center;'>⚡ People's Mandate AI</h1>
<p style='text-align:center;color:gray;'>Political Intelligence Engine</p>
</div>
""", unsafe_allow_html=True)

# ---------- SIDEBAR ----------
with st.sidebar:

    st.markdown("## ⚡ Mandate")

    # ➕ New Chat
    if st.button("➕ New Chat"):
        chat_id = str(uuid.uuid4())
        st.session_state.chats[chat_id] = []
        st.session_state.current_chat = chat_id

    st.markdown("---")

    # Chat list
    for chat_id in list(st.session_state.chats.keys()):

        col1, col2, col3 = st.columns([6,1,1])
        name = st.session_state.chat_names.get(chat_id, "New Chat")

        # Highlight active chat
        if chat_id == st.session_state.current_chat:
            name = "👉 " + name

        if col1.button(name, key=f"chat_{chat_id}"):
            st.session_state.current_chat = chat_id

        if col2.button("✏️", key=f"rename_{chat_id}"):
            st.session_state.chat_names[chat_id] = f"Chat {len(st.session_state.chat_names)+1}"

        if col3.button("🗑️", key=f"delete_{chat_id}"):
            del st.session_state.chats[chat_id]
            if chat_id in st.session_state.chat_names:
                del st.session_state.chat_names[chat_id]

            if st.session_state.chats:
                st.session_state.current_chat = list(st.session_state.chats.keys())[0]
            else:
                new_id = str(uuid.uuid4())
                st.session_state.chats[new_id] = []
                st.session_state.current_chat = new_id

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

    # Name chat
    if st.session_state.current_chat not in st.session_state.chat_names:
        st.session_state.chat_names[st.session_state.current_chat] = prompt[:30]

    # ---------- SHEET DETECTION ----------
    sheet_descriptions = ""
    for name, df in all_sheets.items():
        cols = ", ".join(df.columns[:10])
        sheet_descriptions += f"\n{name}: {cols}"

    with st.spinner("⚡ Thinking..."):
        sheet_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": f"""
Sheets:
{sheet_descriptions}

Question: {prompt}

Return only best matching sheet name.
"""
            }]
        )

    selected_sheet_raw = sheet_response.choices[0].message.content.strip()

    selected_sheet = next(
        (s for s in sheet_names if s.lower() == selected_sheet_raw.lower()),
        sheet_names[0]
    )

    df = all_sheets[selected_sheet]

    # ---------- FIX NUMERIC ----------
    df = df.apply(lambda col: pd.to_numeric(col, errors='coerce'))

    data_context = df.head(50).to_string(index=False)

    # ---------- AI ANSWER ----------
    with st.spinner("🤖 Analyzing data..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are analyzing '{selected_sheet}' data."},
                {"role": "user", "content": f"Data:\n{data_context}\n\nQuestion: {prompt}"}
            ]
        )

    answer = response.choices[0].message.content
    messages.append({"role": "assistant", "content": answer})

    # ---------- OUTPUT ----------
    with st.chat_message("assistant"):

        st.write(f"📊 Using Sheet: {selected_sheet}")
        st.write(answer)

        numeric_df = df.select_dtypes(include="number")

        if not numeric_df.empty:

            # ---------- SMART VISUAL ----------
            with st.spinner("📊 Building visualization..."):
                viz_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "system",
                        "content": f"""
Columns:
{list(df.columns)}

Question: {prompt}

Reply:
TYPE: bar/line/kpi
COLUMNS: col1,col2
"""
                    }]
                )

            viz_text = viz_response.choices[0].message.content.lower()

            chart_type = "bar"
            selected_cols = numeric_df.columns[:2].tolist()

            if "line" in viz_text:
                chart_type = "line"
            elif "kpi" in viz_text:
                chart_type = "kpi"

            if "columns:" in viz_text:
                try:
                    cols_part = viz_text.split("columns:")[1].strip()
                    selected_cols = [
                        c.strip() for c in cols_part.split(",")
                        if c.strip() in df.columns
                    ]
                except:
                    pass

            try:
                chart_df = df[selected_cols]

                if chart_type == "line":
                    st.line_chart(chart_df)
                elif chart_type == "kpi":
                    col = selected_cols[0]
                    st.metric(f"Top {col}", df[col].max())
                else:
                    st.bar_chart(chart_df)

            except:
                st.bar_chart(numeric_df)

            # ---------- INSIGHT ----------
            insight = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": f"Give short insight from this data: {list(df.columns)}"
                }]
            )

            st.markdown("### 🧠 Insight")
            st.write(insight.choices[0].message.content)

        else:
            st.warning("No numeric data available")

# ---------- SAVE ----------
save_chats(st.session_state.chats)
