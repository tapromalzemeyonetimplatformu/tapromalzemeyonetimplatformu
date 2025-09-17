# ✅ CREDIT_Literature_Reviewer.py (4_CREDIT_Literature_Reviewer.py)
import streamlit as st
import os
import json
from datetime import datetime
from pathlib import Path
import base64

# ✅ Kullanıcı giriş kontrolü
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()
    
st.set_page_config(page_title="CREDIT Literature Reviewer", layout="wide")
st.title("CREDIT Literature Reviewer")

UPLOAD_DIR = "uploaded_literature_credit"
METADATA_FILE = "literature_files_credit.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)

if METADATA_FILE in os.listdir():
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        uploaded_files = json.load(f)
else:
    uploaded_files = []

def save_metadata():
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(uploaded_files, f, indent=4)

def file_uploader():
    st.subheader("📤 Upload a new literature file")

    uploaded_file = st.file_uploader("Upload file", type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls", "csv", "docx", "pptx"], label_visibility="collapsed")
    title = st.text_input("Enter a title for this file")
    description = st.text_area("Enter a description for this file")

    if st.button("Upload") and uploaded_file and title:
        file_bytes = uploaded_file.read()
        file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        uploaded_files.append({
            "filename": uploaded_file.name,
            "title": title,
            "description": description,
            "uploader": st.session_state.get("username", "anonymous"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_metadata()
        st.success("File uploaded successfully.")
        st.rerun()

def display_uploaded_files():
    st.subheader("📁 Uploaded Files")
    for i, file in enumerate(uploaded_files):
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 2, 3, 2, 2, 1, 1, 1])
        col1.write(f"**Original:** {file['filename']}")
        col2.write(f"**Title:** {file['title']}")
        col3.write(f"**Description:** {file['description']}")
        col4.write(f"**Uploader:** {file['uploader']}")
        col5.write(f"**Date:** {file['timestamp']}")

        # Delete button
        if col6.button("❌", key=f"delete_{file['filename']}"):
            file_path = os.path.join(UPLOAD_DIR, file['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            uploaded_files.pop(i)
            save_metadata()
            st.rerun()

        # Download button
        with open(os.path.join(UPLOAD_DIR, file['filename']), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            href = f'<a href="data:file/octet-stream;base64,{b64}" download="{file["filename"]}">📥</a>'
            col7.markdown(href, unsafe_allow_html=True)

        # Preview toggle button
        if col8.button("👁️", key=f"preview_{file['filename']}"):
            st.session_state[f"show_preview_{file['filename']}"] = not st.session_state.get(f"show_preview_{file['filename']}", False)

        # Conditional preview section
        if st.session_state.get(f"show_preview_{file['filename']}", False):
            st.markdown(f"### 👁️ Preview: {file['title']}")
            file_path = os.path.join(UPLOAD_DIR, file['filename'])
            if file['filename'].lower().endswith((".png", ".jpg", ".jpeg")):
                st.image(file_path, use_column_width=True)
            else:
                st.markdown(
                    """
                    <div style='text-align: center; padding: 1em; border: 2px dashed #999; border-radius: 10px; background-color: #1e1e1e; color: #ddd;'>
                        🔒 <strong>Preview not available for this file type.</strong>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            st.markdown("---")

file_uploader()
display_uploaded_files()
