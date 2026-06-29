import streamlit as st
import pandas as pd
from openai import OpenAI

# --------------------------
# OpenAI
# --------------------------
client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

# --------------------------
# Page Config
# --------------------------
st.set_page_config(
    page_title="People's Mandate AI",
    layout="wide"
)

st.markdown("""
<style>
body {
    background-color: #0e1117;
}

.stChatMessage {
    border-radius: 12px;
    padding: 10px;
}

h1 {
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

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
# Chat Memory
# --------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# --------------------------
# Show Chat
# --------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --------------------------
# User Question
# --------------------------
if prompt := st.chat_input(
    "Ask anything about your political data..."
):

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):
        st.write(prompt)

    # --------------------------
    # Build Sheet Descriptions
    # --------------------------
    sheet_descriptions = ""

    for name, df in all_sheets.items():

        cols = ", ".join(
            map(str, df.columns)
        )

        sample = df.head(3).to_string(
            index=False
        )

        sheet_descriptions += f"""

Sheet: {name}

Columns:
{cols}

Sample Data:
{sample}

"""

    # --------------------------
    # AI Chooses Sheet
    # --------------------------
    sheet_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""
You are a political data expert.

Below are sheets with columns
and sample data.

{sheet_descriptions}

User Question:
{prompt}

Choose ONLY one sheet name.
Return only the sheet name.
No explanation.
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

    # --------------------------
    # Search Matching Rows
    # --------------------------
    try:

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

    except:
        matches = pd.DataFrame()

    # --------------------------
    # Data Context
    # --------------------------
    if not matches.empty:

        data_context = (
            matches
            .head(100)
            .to_string(index=False)
        )

    else:

        data_context = (
            df
            .head(100)
            .to_string(index=False)
        )

    # --------------------------
    # Final Answer
    # --------------------------
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""
You are People's Mandate AI.

Use ONLY the supplied data.

If information is unavailable,
say:
'No matching information found
in the dataset.'

Never make up facts.
"""
            },
            {
                "role": "user",
                "content":
                f"""
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

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    # --------------------------
    # Show Answer
    # --------------------------
    with st.chat_message(
        "assistant"
    ):

        st.info(
            f"📊 Using Sheet: {selected_sheet}"
        )

        st.write(answer)

        st.caption(
            f"Rows Analysed: {len(df)}"
        )

        numeric_df = df.select_dtypes(
            include="number"
        )

        if not numeric_df.empty:
            st.bar_chart(numeric_df)
