import streamlit as st
import openai
import json
import fitz  # PyMuPDF for PDFs
import docx  # for Word documents
import os

# 🔐 Set your password here
PASSWORD = "trackrecordanalysistool"

# ✅ Secure API key (or paste directly if not using secrets)
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
def rate_cv(cv_text, rubric_text):
    messages = [
        {"role": "system", "content": rubric_text},
        {"role": "user", "content": f"""
Please rate the following CV using the rubric provided above. There are six categories.

Return the result as valid JSON in the following format:
{{
  "Category Name": {{
    "rating_numeric": 1-10,
    "rating_word": "Excellent / Good / Fair / Poor / etc.",
    "justification": "A short explanation..."
  }},
  ...
}}

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

# File upload and CV rating
st.write("Upload a CV file (.txt, .pdf, or .docx) to get it rated across 15 categories using your custom rubric.")
uploaded_file = st.file_uploader("Upload CV", type=["txt", "pdf", "docx"])

if uploaded_file:
    cv_text = extract_text(uploaded_file)

    if cv_text:
        if st.button("Rate CV"):
            with st.spinner("Rating in progress..."):
                rubric = load_rubric()
                result = rate_cv(cv_text, rubric)
                try:
                    parsed = json.loads(result)
                    st.success("Rating complete!")
                    st.json(parsed)
                except Exception as e:
                    st.error("Something went wrong. Output could not be parsed.")
                    st.code(result)
    else:
        st.error("Unsupported file format or failed to extract text.")

