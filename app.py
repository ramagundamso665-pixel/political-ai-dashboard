import streamlit as st
import pandas as pd
import json
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(
    page_title="People's Mandate AI",
    layout="wide"
)

st.title("🗳️ People's Mandate AI")

client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

# -----------------------------
# LOAD EXCEL
# -----------------------------
@st.cache_data
def load_data():
    return pd.read_excel(
        "Book 13.xlsx",
        sheet_name=None
    )

all_sheets = load_data()

# -----------------------------
# CHAT MEMORY
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------
# BUILD SCHEMA
# -----------------------------
schema = ""

for sheet_name, df in all_sheets.items():

    cols = ", ".join(
        map(str, df.columns)
    )

    sample = (
        df.head(2)
        .to_string(index=False)
    )

    schema += f"""
Sheet: {sheet_name}

Columns:
{cols}

Sample:
{sample}

"""

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
SYSTEM_PROMPT = f"""
You are People's Mandate AI.

Available sheets:

{schema}

Return ONLY JSON.

Example:

{{
    "sheet":"Campaign_Activity",
    "analysis_type":"count",
    "chart":"table"
}}

analysis_type:
summary
count
list
compare
trend
distribution
ranking

chart:
table
bar
line
area
pie

Never return explanation.
Return only JSON.
"""

# -----------------------------
# SHOW OLD CHAT
# -----------------------------
for msg in st.session_state.messages:
    with st.chat_message(
        msg["role"]
    ):
        st.write(
            msg["content"]
        )

# -----------------------------
# ASK QUESTION
# -----------------------------
if prompt := st.chat_input(
    "Ask anything about your political data..."
):

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message(
        "user"
    ):
        st.write(prompt)

    # -----------------------------
    # QUERY PLANNER
    # -----------------------------
    try:

        planner = (
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
        )

        raw = (
            planner
            .choices[0]
            .message
            .content
        )

        cleaned = (
            raw
            .replace(
                "```json",
                ""
            )
            .replace(
                "```",
                ""
            )
            .strip()
        )

        plan = json.loads(
            cleaned
        )

    except Exception as e:

        st.error(
            "Planner Error"
        )
        st.exception(e)
        st.stop()

    # -----------------------------
    # GET SHEET
    # -----------------------------
    sheet_raw = plan.get(
        "sheet",
        ""
    )

    selected_sheet = next(
        (
            s
            for s in all_sheets.keys()
            if s.lower()
            == sheet_raw.lower()
        ),
        list(
            all_sheets.keys()
        )[0]
    )

    df = (
        all_sheets[
            selected_sheet
        ]
        .copy()
    )

    # -----------------------------
    # SEND DATA TO GPT
    # -----------------------------
    data_context = (
        df.head(100)
        .to_string(
            index=False
        )
    )

    response = (
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content":
                    f"""
You are People's Mandate AI.

Answer ONLY from:

{selected_sheet}

Never make up facts.

If data does not exist,
say:

'No information available in the dataset.'
"""
                },
                {
                    "role": "user",
                    "content":
                    f"""
Question:

{prompt}

Data:

{data_context}
"""
                }
            ]
        )
    )

    answer = (
        response
        .choices[0]
        .message
        .content
    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    # -----------------------------
    # SHOW RESULT
    # -----------------------------
    with st.chat_message(
        "assistant"
    ):

        st.info(
            f"📊 Using Sheet: {selected_sheet}"
        )

        st.write(answer)

        # -----------------------------
        # AUTO CHARTS
        # -----------------------------
        numeric_df = (
            df.select_dtypes(
                include="number"
            )
        )

        if not numeric_df.empty:

            chart = plan.get(
                "chart",
                "bar"
            )

            if chart == "line":
                st.line_chart(
                    numeric_df
                )

            elif chart == "area":
                st.area_chart(
                    numeric_df
                )

            else:
                st.bar_chart(
                    numeric_df
                )

        st.dataframe(
            df.head(20)
        )
