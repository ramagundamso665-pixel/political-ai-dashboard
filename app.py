import streamlit as st
import pandas as pd
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("⚡ Mandate AI")

# ---------- LOAD ALL DATA (HIDDEN) ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)

# Combine all sheets into one dataframe
df = pd.concat(all_sheets.values(), ignore_index=True)

# ---------- USER INPUT ----------
question = st.text_input("Ask anything about your data...")

# ---------- AI LOGIC ----------
if question:
    data_context = df.head(100).to_string(index=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are a data analyst.

Use ONLY the given dataset.

If the question requires visualization:
Respond exactly like:
CHART: yes
TYPE: bar/line

Otherwise:
CHART: no

Also provide clear answer.
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

    # ---------- AUTO CHART ----------
    if "CHART: yes" in output:
        numeric_df = df.select_dtypes(include="number")

        if "line" in output:
            st.line_chart(numeric_df)
        else:
            st.bar_chart(numeric_df)
