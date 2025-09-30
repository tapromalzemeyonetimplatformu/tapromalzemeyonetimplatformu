import streamlit as st

# Sayfa başlığı ve düzeni
st.set_page_config(page_title="Home", page_icon="🏠", layout="wide")

# Sayfa başlığı
st.title("🏠 Welcome to TA & PRO Common Space")

col1, col2 = st.columns(2)

with col1:
    st.image("images/logo1.jpg", caption="Turkish Aerospace", width=450)

with col2:
    st.image("images/logo2.jpg", caption="Prodigma", width=450)
    
# Yan menüdeki seçenekler
page = st.sidebar.radio("📁 Navigation", [
    "Material Selector",
    "Literature Reviewer",
    "Tensile Test Library",
    "DSC Library",
    "SEM & EDS Library",
    "Fatigue Test Library",
    "Production Tracker"
])

# Seçilen menüye göre sayfaya yönlendirme
if page == "COMPADDITIVE Material Selection":
    st.switch_page("pages/1_Material_Selector.py")

elif page == "COMPADDITIVE Literature Reviewer":
    st.switch_page("pages/2_Literature_Reviewer.py")

elif page == "Tensile Test Library":
    st.switch_page("pages/3_Tensile_Test_Library.py")

elif page == "DSC Library":
    st.switch_page("pages/4_DSC_Library.py")

elif page == "SEM & EDS Library":
    st.switch_page("pages/5_SEM_&_EDS_Library.py")

elif page == "Fatigue Test Library":
    st.switch_page("pages/6_Fatigue_Test_Library.py")

elif page == "Production Tracker":
    st.switch_page("pages/7_Production_Tracker.py")
