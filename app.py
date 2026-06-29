import streamlit as st
import pandas as pd
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="Mandate AI", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- HEADER ----------
st.markdown("""
<h1 style='text-align:center;'>⚡ Mandate AI</h1>
<p style='text-align:center;color:gray;'>AI-powered political intelligence</p>
""", unsafe_allow_html=True)

st.markdown("---")

# ---------- LOAD DATA ----------
all_sheets = pd.read_excel("Book 13.xlsx", sheet_name=None)

sheet_names = list(all_sheets.keys())
selected_sheet = st.selectbox("📊 Select Data Sheet", sheet_names)

df = all_sheets[selected_sheet]

# ---------- DASHBOARD ----------
st.markdown("## 📊 Data Overview")

col1, col2, col3 = st.columns(3)

col1.metric("Rows", df.shape[0])
col2.metric("Columns", df.shape[1])
col3.metric("Sheet", selected_sheet)

st.dataframe(df, use_container_width=True)

st.markdown("### 📈 Data Visualization")
st.bar_chart(df.select_dtypes(include="number"))

st.markdown("---")

# ---------- AI SECTION ----------
st.markdown("## 💬 Ask AI About Your Data")

question = st.text_input("Ask anything from this data...")

if question:
    data_context = df.head(100).to_string(index=False)  # limit for speed

    with st.spinner("Analyzing your data..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are a political data analyst. Answer ONLY using the provided dataset: {selected_sheet}."},
                {"role": "user", "content": f"Dataset:\n{data_context}\n\nQuestion: {question}"}
            ]
        )

        answer = response.choices[0].message.content

    st.success("Answer:")
    st.write(answer)
