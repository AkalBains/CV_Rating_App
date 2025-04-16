import streamlit as st
import openai
import json
import fitz  # PyMuPDF
import docx
import os
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 🔐 Credentials
PASSWORD = st.secrets["ACCESS_PASSWORD"]
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
gc = gspread.authorize(credentials)
SHEET_NAME = "Track Record Ratings"
sheet = gc.open(SHEET_NAME).sheet1

# Session state for persistent scoring
if "gpt_result" not in st.session_state:
    st.session_state.gpt_result = ""
if "gpt_score" not in st.session_state:
    st.session_state.gpt_score = None
if "gpt_category_scores" not in st.session_state:
    st.session_state.gpt_category_scores = {}

# Load rubric
def load_rubric():
    with open("scoring_instructions.txt", "r", encoding="utf-8") as f:
        return f.read()

# Text extraction
def extract_text(file):
    if file.type == "text/plain":
        return file.read().decode("utf-8")
    elif file.type == "application/pdf":
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text
    elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    return None

# GPT scoring
def rate_cv(cv_text, rubric_text, role):
    prompt = f"""
You are a CV scoring assistant. You will score the following CV across six precise categories.

Use ONLY the instructions from the rubric provided in the system prompt. DO NOT use prior knowledge or assumptions.

The six categories are:
1. Education
2. Industry Experience
3. Range of Experience
4. Benchmark of Career Exposure
5. Average Length of Stay at Firms
6. Within Firm

For each category:
- Assign a word-based rating (e.g. Low, Moderate, Strong)
- Provide a clear justification

Return output like:
Education: Strong - Explanation...
...
Total Score: <sum of numeric equivalents>

Conversion rules:
low/none/no = 0
moderate/notable/legacy = 1
sound/single instance/yes = 2
strong = 3
exceptional/thematic = 5

CV:
\"\"\"{cv_text}\"\"\"

Role being considered for: {role}
"""
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.2)
    return response.choices[0].message.content

# Extract individual GPT category scores
def extract_gpt_scores(text):
    score_map = {
        "low": 0, "none": 0, "no": 0,
        "moderate": 1, "notable": 1, "legacy": 1,
        "sound": 2, "single instance": 2, "yes": 2,
        "strong": 3, "exceptional": 5, "thematic": 5
    }

    categories = [
        "Education", "Industry Experience", "Range of Experience",
        "Benchmark of Career Exposure", "Average Length of Stay at Firms", "Within Firm"
    ]

    scores = {f"GPT_{cat}": 0 for cat in categories}
    scores["GPT Score"] = 0

    for line in text.splitlines():
        for cat in categories:
            if line.lower().startswith(cat.lower()):
                parts = line.split(":")
                if len(parts) > 1:
                    rating_part = parts[1].strip().split("-")[0].strip().lower()
                    scores[f"GPT_{cat}"] = score_map.get(rating_part, 0)
        if "total score" in line.lower():
            match = re.search(r"(\d+)", line)
            if match:
                scores["GPT Score"] = int(match.group(1))

    return scores

# UI
st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔒 CV Rating App (GPT-4o)")

# Login
if st.text_input("Enter password to access the app:", type="password") != PASSWORD:
    st.warning("Access restricted.")
    st.stop()

# Consultant info
consultant = st.text_input("👤 Consultant Name")
candidate = st.text_input("🧑 Candidate Name")
role = st.text_input("📌 Role Being Considered For")
company = st.text_input("🏢 Company Being Considered For")
uploaded_file = st.file_uploader("📄 Upload CV", type=["txt", "pdf", "docx"])

if uploaded_file and role:
    cv_text = extract_text(uploaded_file)
    if cv_text and st.button("Run GPT Scoring"):
        with st.spinner("Scoring with GPT..."):
            rubric = load_rubric()
            result = rate_cv(cv_text, rubric, role)
            st.session_state.gpt_result = result
            st.session_state.gpt_category_scores = extract_gpt_scores(result)
            st.session_state.gpt_score = st.session_state.gpt_category_scores["GPT Score"]
            st.success("GPT scoring complete!")

if st.session_state.gpt_result:
    st.markdown("### 🧐 GPT Rating")
    st.markdown(st.session_state.gpt_result)

# Consultant input
if uploaded_file:
    st.subheader("📝 Consultant Input")
    consultant_inputs = {
        "Extracurricular Activities": st.selectbox("Extracurricular Activities", ["low", "moderate", "sound", "strong", "exceptional"]),
        "Challenges in Starting Base": st.selectbox("Challenges in Starting Base", ["low", "moderate", "notable", "strong", "exceptional"]),
        "Level of Experience": st.selectbox("Level of Experience", ["low", "moderate", "sound", "strong"]),
        "Geographic Experience": st.selectbox("Geographic Experience", ["low", "moderate", "sound", "strong"]),
        "Speed of Career Progression": st.selectbox("Speed of Career Progression", ["low", "moderate", "strong", "exceptional"]),
        "Internal Career Progression": st.selectbox("Internal Career Progression", ["low", "moderate", "strong", "exceptional"]),
        "Recent Career Progression": st.selectbox("Recent Career Progression", ["low", "moderate", "strong", "exceptional"]),
        "Career Moves Facilitated by Prior Colleagues": st.selectbox("Career Moves Facilitated by Prior Colleagues", ["none", "single instance", "thematic"]),
        "Regretted Career Choices": st.selectbox("Regretted Career Choices", ["none", "single instance", "thematic"]),
        "Regretted Personal Choices": st.selectbox("Regretted Personal Choices", ["none", "single instance", "thematic"])
    }

    score_map = {
        "low": 0, "none": 0, "no": 0,
        "moderate": 1, "notable": 1, "legacy": 1,
        "sound": 2, "single instance": 2, "yes": 2,
        "strong": 3, "exceptional": 5, "thematic": 5
    }

    if st.button("Calculate Total Score"):
        consultant_score = 0
        st.markdown("### 👤 Consultant Ratings")
        for category, rating in consultant_inputs.items():
            score = score_map.get(rating.lower(), 0)
            if category in ["Regretted Career Choices", "Regretted Personal Choices"]:
                consultant_score -= score
                st.markdown(f"- **{category}**: {rating.capitalize()} (−{score})")
            else:
                consultant_score += score
                st.markdown(f"- **{category}**: {rating.capitalize()} (+{score})")

        gpt_score = st.session_state.gpt_score or 0
        total_score = consultant_score + gpt_score
        st.markdown(f"### 🧮 Consultant Score: **{consultant_score}**")
        st.markdown(f"### 🤖 GPT Score: **{gpt_score}**")
        st.markdown(f"### ✅ Total Score: {total_score}")
        st.markdown("### 📊 Benchmark Score: 22")

        row = [
            datetime.now().isoformat(),
            consultant, candidate, role, company,
            gpt_score,
            consultant_score,
            total_score
        ]

        # Add all GPT category scores
        for cat in [
            "Education", "Industry Experience", "Range of Experience",
            "Benchmark of Career Exposure", "Average Length of Stay at Firms", "Within Firm"
        ]:
            row.append(st.session_state.gpt_category_scores.get(f"GPT_{cat}", 0))

        # Add consultant category scores
        for category in consultant_inputs:
            score = score_map.get(consultant_inputs[category].lower(), 0)
            if category in ["Regretted Career Choices", "Regretted Personal Choices"]:
                score *= -1
            row.append(score)

        sheet.append_row(row)

