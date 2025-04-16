import streamlit as st
import openai
import json
import fitz  # PyMuPDF for PDFs
import docx  # for Word documents
import os
import re  # For GPT total extraction

# 🔐 Secure credentials
PASSWORD = st.secrets["ACCESS_PASSWORD"]
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Load scoring rubric
def load_rubric():
    with open("scoring_instructions.txt", "r", encoding="utf-8") as f:
        return f.read()

# Extract text from uploaded CV
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
    else:
        return None

# Call GPT to rate CV
def rate_cv(cv_text, rubric_text, role):
    prompt = f"""
Please rate the following CV using the rubric provided above, in the context of the role: "{role}".

There are six categories. For each category, provide:
- A numeric rating (1–5)
- A word-based rating (e.g., Exceptional / Strong / Sound / Moderate / etc)
- A short justification

Translate the word-based rating into a score using this mapping:
low/none = 0, moderate = 1, sound/single instance = 2, strong = 3, exceptional/thematic = 5

Return the total as:
Total: <sum>

Present the output in a clean, readable format using markdown, not as JSON.

CV:
\"\"\"{cv_text}\"\"\"
"""

    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": prompt}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2
    )
    return response.choices[0].message.content

# Streamlit UI
st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔐 CV Rating App (GPT-4o)")

# Password gate
password = st.text_input("Enter password to access the app:", type="password")
if password != PASSWORD:
    st.warning("Access restricted. Please enter the correct password.")
    st.stop()

# Role and file input
role = st.text_input("🔍 What role is this CV being considered for?")
uploaded_file = st.file_uploader("Upload CV (.txt, .pdf, or .docx)", type=["txt", "pdf", "docx"])

if uploaded_file and role:
    cv_text = extract_text(uploaded_file)

    if cv_text:
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

        # Rating-to-score mapping
        score_map = {
            "low": 0,
            "none": 0,
            "no": 0,
            "moderate": 1,
            "notable": 1,
            "legacy": 1,
            "sound": 2,
            "single instance": 2,
            "yes": 2,
            "strong": 3,
            "exceptional": 5,
            "thematic": 5
        }

        if st.button("Rate CV"):
            with st.spinner("Rating in progress..."):
                rubric = load_rubric()
                gpt_result = rate_cv(cv_text, rubric, role)

                st.success("Rating complete!")

                st.markdown("### 🧐 GPT Rating")
                st.markdown(gpt_result)

                st.markdown("### 👤 Consultant Ratings")
                consultant_score = 0

                for category, rating in consultant_inputs.items():
                    score = score_map.get(rating.lower(), 0)
                    if category in ["Regretted Career Choices", "Regretted Personal Choices"]:
                        consultant_score -= score
                        st.markdown(f"- **{category}**: {rating.capitalize()} (−{score})")
                    else:
                        consultant_score += score
                        st.markdown(f"- **{category}**: {rating.capitalize()} (+{score})")

                # ✅ Extract GPT score using regex
                gpt_score = 0
                match = re.search(r"Total:\s*(\d+)", gpt_result)
                if match:
                    gpt_score = int(match.group(1))

                # Final scores
                st.markdown(f"### 🧮 Consultant Score: **{consultant_score}**")
                st.markdown(f"### 🤖 GPT Score: **{gpt_score}**")

                total_score = consultant_score + gpt_score
                st.markdown(f"### ✅ **Total Aggregate Score: {total_score}**")
                st.markdown(f"### 📊 **Benchmark Score: 22**")
    else:
        st.error("Unsupported file format or failed to extract text.")

