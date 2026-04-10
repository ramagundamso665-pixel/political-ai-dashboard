import streamlit as st
import pandas as pd
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("⚡ Mandate AI")

# ---------- LOAD DATA ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)

sheet_names = list(all_sheets.keys())
selected_sheet = st.selectbox("Select Data Sheet", sheet_names)

df = all_sheets[selected_sheet]

st.dataframe(df)

# ---------- USER QUESTION ----------
question = st.text_input("Ask anything about your data...")

if question:
    data_context = df.head(100).to_string(index=False)

    with st.spinner("Analyzing..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
You are a data analyst.

Based on the user's question:
1. Answer using the dataset
2. Decide if a chart is needed
3. If chart needed, say which type (bar/line) and which columns

Respond in this format:
ANSWER: <text>
CHART: <yes/no>
TYPE: <bar/line>
COLUMNS: <column names>
"""
                },
                {
                    "role": "user",
                    "content": f"DATA:\n{data_context}\n\nQUESTION: {question}"
                }
            ]
        )

    output = response.choices[0].message.content
    st.write(output)

    # ---------- SIMPLE PARSING ----------
    if "CHART: yes" in output:
        numeric_df = df.select_dtypes(include="number")

        if "TYPE: line" in output:
            st.line_chart(numeric_df)
        else:
            st.bar_chart(numeric_df)
