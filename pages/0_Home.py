import streamlit as st

# Sayfa başlığı ve düzeni
st.set_page_config(page_title="Home", page_icon="🏠", layout="wide")

# Sayfa başlığı
st.title("🏠 Welcome to TA & PRO Common Space")

# Yan menüdeki seçenekler
page = st.sidebar.radio("📁 Navigation", [
    "COMPADDITIVE Material Selection",
    "COMPADDITIVE Literature Reviewer",
    "CREDIT Literature Reviewer",
    "Tensile Test Library",
    "DSC Library",
    "SEM & EDS Library",
    "Fatigue Test Library",
    "Production Tracker"
])

# Seçilen menüye göre sayfaya yönlendirme
if page == "COMPADDITIVE Material Selection":
    st.switch_page("pages/1_COMPADDITIVE_Material_Selection.py")

elif page == "COMPADDITIVE Literature Reviewer":
    st.switch_page("pages/2_COMPADDITIVE_Literature_Reviewer.py")

elif page == "CREDIT Literature Reviewer":
    st.switch_page("pages/3_CREDIT_Literature_Reviewer.py")

elif page == "Tensile Test Library":
    st.switch_page("pages/4_Tensile_Test_Library.py")

elif page == "DSC Library":
    st.switch_page("pages/5_DSC_Library.py")

elif page == "SEM & EDS Library":
    st.switch_page("pages/6_SEM_&_EDS_Library.py")

elif page == "Fatigue Test Library":
    st.switch_page("pages/7_Fatigue_Test_Library.py")

elif page == "Production Tracker":
    st.switch_page("pages/8_Production_Tracker.py")
