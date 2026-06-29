# --------------------------
# Memory Variables
# --------------------------
if "last_sheet" not in st.session_state:
    st.session_state.last_sheet = None

if "last_rows" not in st.session_state:
    st.session_state.last_rows = None

if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

# --------------------------
# Detect Follow-up Questions
# --------------------------
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

# --------------------------
# Get Sheet and Data
# --------------------------
if (
    is_followup
    and st.session_state.last_sheet is not None
    and st.session_state.last_rows is not None
):

    selected_sheet = st.session_state.last_sheet
    matches = st.session_state.last_rows
    df = all_sheets[selected_sheet]

else:

    sheet_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""
You are a political data expert.

Below are sheets with columns and sample data.

{sheet_descriptions}

User Question:
{prompt}

Return ONLY the best matching sheet name.
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
            if s.lower() == selected_sheet_raw.lower()
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

# --------------------------
# Data Context
# --------------------------
if not matches.empty:
    data_context = matches.head(100).to_string(index=False)
else:
    data_context = df.head(100).to_string(index=False)

# --------------------------
# GPT Answer
# --------------------------
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": """
You are People's Mandate AI.

Answer ONLY from the provided data.
Never make up facts.

If information is unavailable, say:
'No matching information found in the dataset.'
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

answer = response.choices[0].message.content

# --------------------------
# Save Memory
# --------------------------
st.session_state.last_sheet = selected_sheet
st.session_state.last_rows = matches
st.session_state.last_answer = answer
