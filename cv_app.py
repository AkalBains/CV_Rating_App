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

# Set up Google Sheets credentials
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

# 3. GPT SCORING

def rate_cv(cv_text, rubric_text, role):
    prompt = f"""
You are a CV scoring assistant. You will score the following CV across six precise categories.

💡 Use ONLY the instructions from the rubric provided in the system prompt. DO NOT use prior knowledge or assumptions. Follow the decision rules exactly.

The six categories are:
1. Education
2. Industry Experience
3. Range of Experience
4. Benchmark of Career Exposure
5. Average Length of Stay at Firms
6. Within Firm

For each category:
- Determine the score using the rubric provided
- Give a numeric score (e.g., 0–5)
- Include a clear explanation (justification)

📊 At the end, return:
- A full breakdown with numbered categories
- A `Total Score:` line showing the total sum of all six numeric scores

CV to evaluate:
\"\"\"{cv_text}\"\"\"

Role being considered for: {role}
"""
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.2)
    return response.choices[0].message.content

def extract_gpt_score(text):
    for line in text.splitlines():
        if "total" in line.lower():
            match = re.search(r"(\d+)", line)
            if match:
                return int(match.group(1))
    return 0

# 4. STREAMLIT UI


def extract_gpt_scores(text):
    categories = [
        "Education", "Industry Experience", "Range of Experience",
        "Benchmark of Career Exposure", "Average Length of Stay at Firms", "Within Firm"
    ]
    scores = {f"GPT_{cat}": 0 for cat in categories}
    current_cat = None

    for line in text.splitlines():
        for cat in categories:
            if cat.lower() in line.lower():
                current_cat = f"GPT_{cat}"
                break
        if "numeric rating" in line.lower() and current_cat:
            match = re.search(r"(\d+)", line)
            if match:
                scores[current_cat] = int(match.group(1))
                current_cat = None
        elif "total" in line.lower() and "numeric" in line.lower():
            match = re.search(r"(\d+)", line)
            if match:
                scores["GPT Score"] = int(match.group(1))
    return scores

st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔒 CV Rating App (GPT-4o)")

# Password protection
if st.text_input("Enter password to access the app:", type="password") != PASSWORD:
    st.warning("Access restricted. Please enter the correct password.")
    st.stop()

# Consultant inputs
consultant = st.text_input("👤 Consultant Name")
candidate = st.text_input("🧑 Candidate Name")
role = st.text_input("📌 Role Being Considered For")
company = st.text_input("🏢 Company Being Considered For")
uploaded_file = st.file_uploader("📄 Upload CV (.txt, .pdf, or .docx)", type=["txt", "pdf", "docx"])

gpt_result = ""
gpt_score = None
cv_text = ""

if uploaded_file and role:
    cv_text = extract_text(uploaded_file)
    if cv_text:
        if st.button("Run GPT Scoring"):
            with st.spinner("Scoring with GPT..."):
                rubric = load_rubric()
                gpt_result = rate_cv(cv_text, rubric, role)
                gpt_scores = extract_gpt_scores(gpt_result)
                gpt_score = gpt_scores.get("GPT Score", 0)
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

            st.markdown(f"### 🧮 Consultant Score: **{consultant_score}**")
            if gpt_score is not None:
                st.markdown(f"### 🤖 GPT Score: **{gpt_score}**")
                total_score = consultant_score + gpt_score
            else:
                st.markdown("### 🤖 GPT Score: *(not yet generated)*")
                total_score = consultant_score

            st.markdown(f"### ✅ Total Score: {total_score}")
            st.markdown("### 📊 Benchmark Score: 22")

            # Save to Google Sheet

            extended_row = [
                datetime.now().isoformat(),
                consultant,
                candidate,
                role,
                company,
                gpt_score if gpt_score is not None else "N/A",
                consultant_score,
                total_score
            ] + [score_map.get(consultant_inputs[cat].lower(), 0) for cat in consultant_inputs]

            sheet.append_row(extended_row)
                datetime.now().isoformat(),
                consultant,
                candidate,
                role,
                company,
                gpt_score if gpt_score is not None else "N/A",
                consultant_score,
                total_score
            ])
