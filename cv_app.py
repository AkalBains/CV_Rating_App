import streamlit as st
import openai
import json
import fitz  # PyMuPDF for PDFs
import docx  # for Word documents
import os

# 🔐 Set your password here (from secrets)
PASSWORD = st.secrets["ACCESS_PASSWORD"]

# ✅ Secure API key (from secrets)
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Load the rubric from file
def load_rubric():
    with open("scoring_instructions.txt", "r", encoding="utf-8") as f:
        return f.read()

# Extract plain text from uploaded file
def extract_text(file):
    if file.type == "text/plain":
        return file.read().decode("utf-8")
    elif file.type == "application/pdf":
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text
    elif file.type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        doc = docx.Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    else:
        return None

# Call GPT to rate the CV
def rate_cv(cv_text, rubric_text, role):
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": f"""
Please rate the following CV using the rubric provided above, in the context of the role: "{role}".

There are six categories. For each category, provide:
- A numeric rating (1–5)
- A word-based rating (e.g., Exceptional / Strong / Sound / Moderate / etc)
- A short justification

Present the output in a clean, readable format using markdown, not as JSON.

CV:
\"\"\"{cv_text}\"\"\"
"""}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2
    )

    return response.choices[0].message.content

# Streamlit UI
st.set_page_config(page_title="CV Rating App", page_icon="📄")
st.title("🔒 CV Rating App (GPT-4o)")

# 🔐 Password protection
password = st.text_input("Enter password to access the app:", type="password")

if password != PASSWORD:
    st.warning("Access restricted. Please enter the correct password.")
    st.stop()

# Role input
role = st.text_input("🔍 What role is this CV being considered for?")

# File upload and CV rating
st.write("Upload a CV file (.txt, .pdf, or .docx) to get it rated across 6 categories using your custom rubric.")
uploaded_file = st.file_uploader("Upload CV", type=["txt", "pdf", "docx"])

# Only proceed if both a file and a role have been provided
if uploaded_file and role:
    cv_text = extract_text(uploaded_file)

    if cv_text:
        st.subheader("📝 Consultant Input")
        st.write("Select the appropriate rating for each category:")

        consultant_scores = {
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

        if st.button("Rate CV"):
            with st.spinner("Rating in progress..."):
                rubric = load_rubric()
                result = rate_cv(cv_text, rubric, role)

                st.success("Rating complete!")

                # GPT Output
                st.markdown("### 🤖 GPT Rating")
                st.markdown(result)

                # Consultant Scores
                st.markdown("### 👤 Consultant Ratings")
                for category, rating in consultant_scores.items():
                    st.markdown(f"- **{category}**: {rating.capitalize()}")
    else:
        st.error("Unsupported file format or failed to extract text.")

