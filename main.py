import streamlit as st
from auth import check_credentials

def login():
    st.set_page_config(page_title="Login", page_icon="🔐", layout="centered")
    st.title("🔐 TA & PRO Common Space Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        if check_credentials(username, password):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.success("✅ Login successful! Redirecting...")
            st.switch_page("pages/0_Home.py")
        else:
            st.error("❌ Invalid username or password.")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login()
else:
    st.switch_page("pages/0_Home.py")
