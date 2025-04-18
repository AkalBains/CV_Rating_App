import streamlit as st
import openai
import json
import fitz  # PyMuPDF for PDFs
import docx
import os
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. AUTH & GOOGLE SHEETS SETUP

PASSWORD = st.secrets["ACCESS_PASSWORD"]
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
gc = gspread.authorize(credentials)
SHEET_NAME = "Track Record Ratings"
sheet = gc.open(SHEET_NAME).sheet1

# 2. RUBRIC & CV EXTRACTION FUNCTIONS

def load_rubric():
    with open("scoring_instructions.txt", "r", encoding="utf-8") as f:
        return f.read()

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

# 3. GPT SCORING — WORD ONLY + JUSTIFICATION

def rate_cv(cv_text, rubric_text, role):
    prompt = f"""
You are an evaluator scoring a CV for a role at "{role}".

You MUST evaluate the CV using the scoring rubric that was just provided in full above. Do not rely on any assumptions, and do not introduce criteria that are not present in the rubric.

Score the CV in the following exact order:

1. Education  
2. Industry experience  
3. Range of experience  
4. Benchmark of career exposure  
5. Average length of stay at firms  
6. Within firm alignment

For each one, provide:
- A word-based rating (e.g. low, moderate, sound, strong, exceptional)
- A short justification based on the rubric and the CV content

DO NOT provide numeric ratings. Only provide the word-based rating and justification.

CV:
\"\"\"{cv_text}\"\"\"
"""
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.1)
    return response.choices[0].message.content

def extract_gpt_word_scores(text):
    categories = [
        "Education", "Industry Experience", "Range of Experience",
        "Benchmark of Career Exposure", "Average Length of Stay at Firms", "Within Firm"
    ]
    word_scores = {f"GPT_{cat}": "N/A" for cat in categories}
    current_cat = None

    for line in text.splitlines():
        for cat in categories:
            if cat.lower() in line.lower():
                current_cat = f"GPT_{cat}"
                break
        if current_cat and ":" in line:
            match = re.search(r":\s*(\w[\w\s]*)", line)
            if match:
                word_scores[current_cat] = match.group(1).strip().lower()
                current_cat = None
    return word_scores

score_map = {
    "low": 0, "none": 0, "no": 0,
    "moderate": 1, "notable": 1, "legacy": 1,
    "sound": 2, "single instance": 2, "yes": 2,
    "strong": 3, "exceptional": 5, "thematic": 5
}

# 4. STREAMLIT UI

st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔒 CV Rating App (GPT-4o)")

if "gpt_scored" not in st.session_state:
    st.session_state.gpt_scored = False
if "gpt_result" not in st.session_state:
    st.session_state.gpt_result = ""
if "gpt_words" not in st.session_state:
    st.session_state.gpt_words = {}
if "gpt_score" not in st.session_state:
    st.session_state.gpt_score = None

if st.text_input("Enter password to access the app:", type="password") != PASSWORD:
    st.warning("Access restricted. Please enter the correct password.")
    st.stop()

consultant = st.text_input("👤 Consultant Name")
candidate = st.text_input("🧑 Candidate Name")
role = st.text_input("📌 Role Being Considered For")
company = st.text_input("🏢 Company Being Considered For")
uploaded_file = st.file_uploader("📄 Upload CV (.txt, .pdf, or .docx)", type=["txt", "pdf", "docx"])

cv_text = ""

if uploaded_file and role:
    cv_text = extract_text(uploaded_file)
    if cv_text:
        if st.button("Run GPT Scoring"):
            with st.spinner("Scoring with GPT..."):
                rubric = load_rubric()
                gpt_result = rate_cv(cv_text, rubric, role)
                word_scores = extract_gpt_word_scores(gpt_result)
                gpt_score = sum(score_map.get(val.lower(), 0) for val in word_scores.values())
                st.session_state.gpt_result = gpt_result
                st.session_state.gpt_words = word_scores
                st.session_state.gpt_score = gpt_score
                st.session_state.gpt_scored = True
                st.success("GPT scoring complete!")
                st.markdown("### 🧐 GPT Rating")
                st.markdown(gpt_result)

        st.subheader("📝 Consultant Input")
        consultant_inputs = {
            "Extracurricular Activities": st.selectbox("Extracurricular Activities", ["low", "moderate", "sound", "strong", "exceptional"]),
            "Challenges in Starting Base": st.selectbox("Challenges in Starting Base", ["low", "moderate", "notable", "strong", "exceptional"]),
            "Industry Experience": st.selectbox("Industry Experience", ["low", "moderate", "sound", "strong"]),
            "Level of Experience": st.selectbox("Level of Experience", ["low", "moderate", "sound", "strong"]),
            "Geographic Experience": st.selectbox("Geographic Experience", ["low", "moderate", "sound", "strong"]),
            "Speed of Career Progression": st.selectbox("Speed of Career Progression", ["low", "moderate", "strong", "exceptional"]),
            "Internal Career Progression": st.selectbox("Internal Career Progression", ["low", "moderate", "strong", "exceptional"]),
            "Recent Career Progression": st.selectbox("Recent Career Progression", ["low", "moderate", "strong", "exceptional"]),
            "Career Moves Facilitated by Prior Colleagues": st.selectbox("Career Moves Facilitated by Prior Colleagues", ["none", "single instance", "thematic"]),
            "Regretted Career Choices": st.selectbox("Regretted Career Choices", ["none", "single instance", "thematic"]),
            "Regretted Personal Choices": st.selectbox("Regretted Personal Choices", ["none", "single instance", "thematic"])
        }

        if not st.session_state.gpt_scored:
            st.warning("⚠️ Please run GPT scoring first.")
        else:
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

                gpt_score = st.session_state.gpt_score
                gpt_words = st.session_state.gpt_words
                total_score = consultant_score + gpt_score

                st.markdown(f"### 🧮 Consultant Score: **{consultant_score}**")
                st.markdown(f"### 🤖 GPT Score: **{gpt_score}**")
                st.markdown(f"### ✅ Total Score: {total_score}")
                st.markdown("### 📊 Benchmark Score: 22")

                consultant_scores = [score_map.get(consultant_inputs[cat].lower(), 0) for cat in consultant_inputs]
                gpt_scores_ordered = [score_map.get(gpt_words.get(f"GPT_{cat}", "low").lower(), 0) for cat in [
                    "Education", "Industry Experience", "Range of Experience",
                    "Benchmark of Career Exposure", "Average Length of Stay at Firms", "Within Firm"
                ]]

                extended_row = [
                    datetime.now().isoformat(),
                    consultant,
                    candidate,
                    role,
                    company,
                    gpt_score,
                    consultant_score,
                    total_score
                ] + gpt_scores_ordered + consultant_scores

                sheet.append_row(extended_row)
