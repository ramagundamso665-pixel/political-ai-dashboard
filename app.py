import streamlit as st
import pandas as pd
from openai import OpenAI

# --------------------------
# Page Config
# --------------------------
st.set_page_config(
    page_title="People's Mandate AI",
    layout="wide"
)

# --------------------------
# OpenAI
# --------------------------
client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

# --------------------------
# Session Memory
# --------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_sheet" not in st.session_state:
    st.session_state.last_sheet = None

if "last_rows" not in st.session_state:
    st.session_state.last_rows = None

if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

# --------------------------
# UI
# --------------------------
st.title("🗳️ People's Mandate AI")

# --------------------------
# Load Excel
# --------------------------
all_sheets = pd.read_excel(
    "Book 13.xlsx",
    sheet_name=None
)
sheet_names = list(all_sheets.keys())

# --------------------------
# Show Previous Messages
# --------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --------------------------
# User Input
# --------------------------
if prompt := st.chat_input("Ask anything about your political data..."):

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):
        st.write(prompt)

    # Detect follow-up questions
    follow_words = [
        "those",
        "them",
        "that",
        "these",
        "which",
        "more",
        "details",
        "show me",
        "tell me more"
    ]

    is_followup = any(
        word in prompt.lower()
        for word in follow_words
    )

    # Use previous context if follow-up
    if (
        is_followup
        and st.session_state.last_sheet is not None
        and st.session_state.last_rows is not None
    ):

        selected_sheet = st.session_state.last_sheet
        matches = st.session_state.last_rows
        df = all_sheets[selected_sheet]

    else:

        # Build sheet descriptions
        sheet_descriptions = ""

        for name, df_tmp in all_sheets.items():

            cols = ", ".join(
                map(str, df_tmp.columns)
            )

            sample = df_tmp.head(3).to_string(
                index=False
            )

            sheet_descriptions += f"""
Sheet: {name}
Columns: {cols}

Sample:
{sample}
"""

        # GPT chooses best sheet
        sheet_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are a political data expert.

{sheet_descriptions}

Question:
{prompt}

Return ONLY the sheet name.
"""
                }
            ]
        )

        selected_sheet_raw = (
            sheet_response
            .choices[0]
            .message
            .content
            .strip()
        )

        selected_sheet = next(
            (
                s
                for s in sheet_names
                if s.lower()
                == selected_sheet_raw.lower()
            ),
            sheet_names[0]
        )

        df = all_sheets[selected_sheet]

        matches = df[
            df.astype(str)
            .apply(
                lambda x:
                x.str.contains(
                    prompt,
                    case=False,
                    na=False
                )
            )
            .any(axis=1)
        ]

    # Data context
    if not matches.empty:
        data_context = matches.head(100).to_string(
            index=False
        )
    else:
        data_context = df.head(100).to_string(
            index=False
        )

    # Final answer
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are People's Mandate AI.

Answer ONLY from the data provided.
If information is unavailable,
say:
'No matching information found in the dataset.'

Never make up facts.
"""
            },
            {
                "role": "user",
                "content": f"""
Sheet:
{selected_sheet}

Data:
{data_context}

Question:
{prompt}
"""
            }
        ]
    )

    answer = (
        response
        .choices[0]
        .message
        .content
    )

    # Save memory
    st.session_state.last_sheet = selected_sheet
    st.session_state.last_rows = matches
    st.session_state.last_answer = answer

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    with st.chat_message("assistant"):
        st.info(
            f"📊 Using Sheet: {selected_sheet}"
        )
        st.write(answer)

        numeric_df = df.select_dtypes(
            include="number"
        )

        if not numeric_df.empty:
            st.bar_chart(numeric_df)
