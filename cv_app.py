import streamlit as st
import openai
import fitz  # PyMuPDF
import docx
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 🔐 AUTH & SHEETS SETUP
PASSWORD = st.secrets["ACCESS_PASSWORD"]
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
gc = gspread.authorize(credentials)
sheet = gc.open("Track Record Ratings").sheet1

# 📑 RUBRIC AND TEXT HANDLING
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
    elif file.type.endswith("document"):
        doc = docx.Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""

# 🤖 GPT SCORING (WORD ONLY)
def rate_cv(cv_text, rubric_text, role):
    prompt = f"""
You are an evaluator scoring a CV for a role at "{role}".

Use the rubric provided above to assign a **word-based rating only** (e.g. Exceptional, Strong, Moderate, etc.) to each of the following six categories.

Do not assign any numeric scores. Do not invent your own criteria.

Categories:
1. Education
2. Industry experience
3. Range of experience
4. Benchmark of career exposure
5. Average length of stay at firms
6. Within firm alignment

Return:
**Word Ratings Summary:**
1. Education: <word>
2. Industry experience: <word>
3. Range of experience: <word>
4. Benchmark of career exposure: <word>
5. Average length of stay at firms: <word>
6. Within firm alignment: <word>

CV:
\"\"\"{cv_text}\"\"\"
"""
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(
        model="gpt-4o", messages=messages, temperature=0.1
    )
    return response.choices[0].message.content

# 🧠 SCORE MAPPING
score_map = {
    "low": 0, "none": 0, "no": 0,
    "moderate": 1, "notable": 1, "legacy": 1,
    "sound": 2, "single instance": 2, "yes": 2,
    "strong": 3, "exceptional": 5, "thematic": 5
}

def extract_word_ratings(text):
    categories = [
        "Education", "Industry experience", "Range of experience",
        "Benchmark of career exposure", "Average length of stay at firms", "Within firm alignment"
    ]
    ratings = {}
    for line in text.splitlines():
        for cat in categories:
            if cat.lower() in line.lower():
                match = re.search(r":\s*([\w\s]+)", line)
                if match:
                    ratings[cat] = match.group(1).strip()
    return ratings

# 🌐 STREAMLIT UI
st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔒 CV Rating App (GPT-4o)")

# Password protection
if st.text_input("Enter password to access the app:", type="password") != PASSWORD:
    st.stop()

# Session state
if "gpt_ratings" not in st.session_state:
    st.session_state.gpt_ratings = None
if "gpt_output" not in st.session_state:
    st.session_state.gpt_output = ""
if "gpt_score" not in st.session_state:
    st.session_state.gpt_score = None

# Inputs
consultant = st.text_input("👤 Consultant Name")
candidate = st.text_input("🧑 Candidate Name")
role = st.text_input("📌 Role Being Considered For")
company = st.text_input("🏢 Company Being Considered For")
uploaded_file = st.file_uploader("📄 Upload CV (.txt, .pdf, .docx)", type=["txt", "pdf", "docx"])

# Process CV
if uploaded_file and role:
    cv_text = extract_text(uploaded_file)

    if st.button("Run GPT Scoring"):
        with st.spinner("Running GPT scoring..."):
            rubric = load_rubric()
            gpt_output = rate_cv(cv_text, rubric, role)
            gpt_ratings = extract_word_ratings(gpt_output)
            gpt_score = sum(score_map.get(r.lower(), 0) for r in gpt_ratings.values())

            st.session_state.gpt_output = gpt_output
            st.session_state.gpt_ratings = gpt_ratings
            st.session_state.gpt_score = gpt_score

        st.success("✅ GPT scoring complete!")

    if st.session_state.gpt_output:
        st.markdown("### 🤖 GPT Output")
        st.markdown(st.session_state.gpt_output)

    st.subheader("📝 Consultant Ratings")
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

    if st.session_state.gpt_ratings and st.button("Calculate Total Score"):
        consultant_score = 0
        for cat, rating in consultant_inputs.items():
            val = score_map.get(rating.lower(), 0)
            consultant_score -= val if "Regretted" in cat else -val

        total = consultant_score + st.session_state.gpt_score

        st.markdown(f"### 🧮 Consultant Score: **{consultant_score}**")
        st.markdown(f"### 🤖 GPT Score: **{st.session_state.gpt_score}**")
        st.markdown(f"### ✅ Total Score: **{total}**")
        st.markdown("### 📊 Benchmark Score: 22")

        row = [
            datetime.now().isoformat(),
            consultant,
            candidate,
            role,
            company,
            st.session_state.gpt_score,
            consultant_score,
            total
        ] + [score_map.get(st.session_state.gpt_ratings.get(cat, "").lower(), 0) for cat in [
            "Education", "Industry experience", "Range of experience",
            "Benchmark of career exposure", "Average length of stay at firms", "Within firm alignment"
        ]] + [score_map.get(consultant_inputs[cat].lower(), 0) for cat in consultant_inputs]

        sheet.append_row(row)

