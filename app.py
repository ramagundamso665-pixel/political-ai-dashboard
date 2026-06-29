import streamlit as st
import pandas as pd
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(layout="wide")
st.markdown("""
<style>
body {
    background-color: #0e1117;
}
.stTextInput > div > div > input {
    background-color: #1c1f26;
    color: white;
}
.stChatMessage {
    border-radius: 10px;
    padding: 10px;
}
h1 {
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

st.title("🤖 AI Political Assistant")

# Load all sheets
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)
sheet_names = list(all_sheets.keys())

# Chat memory
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Input
if prompt := st.chat_input("Ask anything..."):

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)

    # 🧠 STEP 1: Build sheet descriptions using columns
    sheet_descriptions = ""

    for name, df in all_sheets.items():
        cols = ", ".join(df.columns[:10])
        sheet_descriptions += f"\n{name}: {cols}"

    # 🧠 STEP 2: AI selects sheet using columns (NOT name guess)
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

    # Match safely
    selected_sheet = next(
        (s for s in sheet_names if s.lower() == selected_sheet_raw.lower()),
        sheet_names[0]
    )

    df = all_sheets[selected_sheet]

    # 🧠 STEP 3: Send limited data
    data_context = df.head(50).to_string(index=False)

    # 🧠 STEP 4: AI answer
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are analyzing '{selected_sheet}' data."},
            {"role": "user", "content": f"Data:\n{data_context}\n\nQuestion: {prompt}"}
        ]
    )

    answer = response.choices[0].message.content

    st.session_state.messages.append({"role": "assistant", "content": answer})

    with st.chat_message("assistant"):
        st.write(f"📊 Using Sheet: {selected_sheet}")
        st.write(answer)

        # Chart
        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            st.bar_chart(numeric_df)
