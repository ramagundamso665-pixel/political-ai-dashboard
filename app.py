import streamlit as st
import pandas as pd
from openai import OpenAI
import json

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("⚡ Mandate AI")

# ---------- LOAD DATA ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)
df = pd.concat(all_sheets.values(), ignore_index=True)

# ---------- INPUT ----------
question = st.text_input("Ask anything about your data...")

if question:
    data_context = df.head(100).to_string(index=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are a professional data analyst.

Analyze the dataset and user's question.

Respond ONLY in JSON format:

{
 "answer": "...",
 "type": "text/chart/kpi",
 "chart_type": "bar/line",
 "columns": ["col1","col2"],
 "kpi": {"name": "...", "value": "..."}
}
"""
            },
            {
                "role": "user",
                "content": f"DATA:\n{data_context}\n\nQUESTION: {question}"
            }
        ]
    )

    output = response.choices[0].message.content

    try:
        result = json.loads(output)

        st.write(result["answer"])

        # ---------- KPI ----------
        if result["type"] == "kpi":
            st.metric(result["kpi"]["name"], result["kpi"]["value"])

        # ---------- CHART ----------
        elif result["type"] == "chart":
            cols = result["columns"]

            if len(cols) >= 2:
                chart_df = df[cols]

                if result["chart_type"] == "line":
                    st.line_chart(chart_df)
                else:
                    st.bar_chart(chart_df)

    except:
        st.write(output)
