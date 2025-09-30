import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import StringIO, BytesIO
import os
import base64
from datetime import datetime
import numpy as np  # hesaplamalar için

# ✅ Kullanıcı giriş kontrolü
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()
    
st.set_page_config(page_title="Tensile Test Library", page_icon="🔬", layout="wide")
st.title("Tensile Test Library")

# Klasör ve metadata ayarları
UPLOAD_DIR = "uploaded_tensile_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
metadata_file = os.path.join(UPLOAD_DIR, "metadata.csv")

# Metadata dosyasını oku veya oluştur
if os.path.exists(metadata_file):
    df_meta = pd.read_csv(metadata_file)
else:
    df_meta = pd.DataFrame(columns=["stored_filename", "original_filename", "user_given_name", "uploader", "timestamp"])
    df_meta.to_csv(metadata_file, index=False)

# 🟦 YÜKLEME ALANI
st.subheader("📤 Upload a new tensile test file")

uploaded_file = st.file_uploader("Upload Excel file", type=["csv", "xlsx"])
user_given_name = st.text_input("Enter a name for this file")

if "username" not in st.session_state:
    st.session_state.username = "unknown"  # login'den gelen veri yoksa

if st.button("Upload") and uploaded_file and user_given_name:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_filename = f"{timestamp}_{uploaded_file.name}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)

    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())

    new_entry = pd.DataFrame([{
        "stored_filename": stored_filename,
        "original_filename": uploaded_file.name,
        "user_given_name": user_given_name,
        "uploader": st.session_state.username,
        "timestamp": timestamp
    }])
    df_meta = pd.concat([df_meta, new_entry], ignore_index=True)
    df_meta.to_csv(metadata_file, index=False)
    st.success("✅ File uploaded successfully. Please refresh the page.")

# 🗂️ Mevcut dosyaların listesini göster
st.subheader("📁 Uploaded Files")

if df_meta.empty:
    st.info("No files uploaded yet.")
else:
    for i, row in df_meta.iterrows():
        col1, col2, col3, col4 = st.columns([3, 3, 2, 1])
        col1.markdown(f"📄 **Original file:** {row['original_filename']}")
        col2.markdown(f"📝 **Name given:** {row['user_given_name']}")
        col3.markdown(f"👤 **Uploader:** {row['uploader']}")

        if col4.button("❌ Delete", key=f"delete_{i}"):
            file_to_delete = os.path.join(UPLOAD_DIR, row["stored_filename"])
            if os.path.exists(file_to_delete):
                os.remove(file_to_delete)

            df_meta = df_meta.drop(i).reset_index(drop=True)
            df_meta.to_csv(metadata_file, index=False)
            st.success(f"Deleted {row['user_given_name']}")
            st.rerun()

# 🟦 VERİ SEÇİMİ VE ANALİZ
st.subheader("📊 Choose data to analyze")

selected_names = st.multiselect(
    label="Select one or more uploaded files to visualize",
    options=df_meta["user_given_name"].tolist()
)

# --- Yardımcı fonksiyonlar (hesaplar) ---
def compute_yield_strength_02_offset(strain_pct: pd.Series, stress_mpa: pd.Series, offset_pct: float = 0.2):
    """
    0.2% offset yöntemiyle akma dayanımı (yield strength) hesaplar.
    - strain_pct: yüzde cinsinden gerinim
    - stress_mpa: MPa cinsinden gerilme
    Geri dönüş: yield_strength_MPa (float) veya None
    """
    s = pd.to_numeric(strain_pct, errors="coerce").to_numpy()
    y = pd.to_numeric(stress_mpa, errors="coerce").to_numpy()
    mask = np.isfinite(s) & np.isfinite(y)
    s, y = s[mask], y[mask]
    if len(s) < 5:
        return None
    try:
        # Elastik bölgeyi yaklaşıkla: %0.05–%0.5 arası, yoksa ilk %5
        lin_mask = (s >= 0.05) & (s <= 0.5)
        if lin_mask.sum() < 5:
            n = max(5, int(len(s) * 0.05))
            s_lin, y_lin = s[:n], y[:n]
        else:
            s_lin, y_lin = s[lin_mask], y[lin_mask]

        m, c = np.polyfit(s_lin, y_lin, 1)  # y = m*s + c
        y_off = m * (s - offset_pct) + c    # offset doğru
        diff = y - y_off

        sign = np.sign(diff)
        changes = np.where(np.diff(sign) != 0)[0]
        if len(changes) == 0:
            # Kesişim yoksa %0.2'deki gerilme
            try:
                ys = float(np.interp(offset_pct, s, y))
                return ys
            except Exception:
                return None

        i = changes[0]
        s1, s2 = s[i], s[i+1]
        d1, d2 = diff[i], diff[i+1]
        s_star = s1 if (d2 - d1) == 0 else s1 - d1 * (s2 - s1) / (d2 - d1)
        ys = float(np.interp(s_star, [s1, s2], [y[i], y[i+1]]))
        return ys
    except Exception:
        return None

def compute_elongation_at_break_pct(strain_pct: pd.Series, stress_mpa: pd.Series):
    """
    Kopma uzaması (%) ~ gerilmenin pozitif olduğu son geçerli noktadaki gerinim.
    """
    s = pd.to_numeric(strain_pct, errors="coerce")
    y = pd.to_numeric(stress_mpa, errors="coerce")
    df = pd.DataFrame({"s": s, "y": y}).dropna()
    positive = df[df["y"] > 0]
    if not positive.empty:
        return float(positive["s"].iloc[-1])
    if not df.empty:
        return float(df["s"].iloc[-1])
    return None

def compute_uts_mpa(stress_mpa: pd.Series):
    """
    UTS (MPa) = gerilmenin ulaştığı maksimum değer.
    """
    y = pd.to_numeric(stress_mpa, errors="coerce")
    if y.dropna().empty:
        return None
    return float(y.max())
# --- Yardımcı fonksiyonlar sonu ---

# Ortak grafik için hazırlık
combined_fig, combined_ax = plt.subplots()
combined_ax.set_xlabel("Uzama (%)")
combined_ax.set_ylabel("Gerilme (MPa)")

# Seçilen her dosya için tablo ve grafik göster
for name in selected_names:
    file_info = df_meta[df_meta["user_given_name"] == name].iloc[0]
    filepath = os.path.join(UPLOAD_DIR, file_info["stored_filename"])

    try:
        if filepath.endswith(".csv"):
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            st.warning(f"📄 Excel files are not yet supported for this analysis.")
            continue

        # Verinin başladığı satırı bul
        start_index = next(i for i, line in enumerate(lines) if "Time measurement" in line)
        table_lines = lines[start_index:]
        df_table = pd.read_csv(StringIO("".join(table_lines)))
        df_clean = df_table[1:].copy()
        df_clean.columns = df_table.iloc[0]
        df_clean.columns = df_clean.columns.str.strip()
        df_clean.columns = ['Time_s', 'Extension_mm', 'Force_N', 'Strain_1', 'Strain_2', 'Stress_MPa']

        df_clean["Strain_2"] = pd.to_numeric(df_clean["Strain_2"], errors="coerce")
        df_clean["Stress_MPa"] = pd.to_numeric(df_clean["Stress_MPa"], errors="coerce")

        df_result = df_clean[["Strain_2", "Stress_MPa"]].copy()
        df_result = df_result.rename(columns={"Strain_2": "Strain (%)", "Stress_MPa": "Stress (MPa)"})

        # Tablo göster
        st.markdown(f"### 📄 Data from: *{name}*")
        st.dataframe(df_result)

        # Grafik oluştur
        fig, ax = plt.subplots()
        ax.plot(df_result["Strain (%)"], df_result["Stress (MPa)"], label=name)
        ax.set_xlabel("Strain (%)")
        ax.set_ylabel("Stress (MPa)")
        ax.set_title(f"Stress-Strain Curve: {name}")
        st.pyplot(fig)

        # ✅ HESAPLAMALAR (grafiğin ALTINDA gösterilecek)
        ys = compute_yield_strength_02_offset(
            df_result["Strain (%)"], df_result["Stress (MPa)"], offset_pct=0.2
        )
        uts = compute_uts_mpa(df_result["Stress (MPa)"])
        e_break = compute_elongation_at_break_pct(
            df_result["Strain (%)"], df_result["Stress (MPa)"]
        )

        # None ise '—' göster
        ys_txt = f"{ys:.2f} MPa" if ys is not None else "—"
        uts_txt = f"{uts:.2f} MPa" if uts is not None else "—"
        eb_txt = f"{e_break:.2f} %" if e_break is not None else "—"

        # ✅ Sonuç kartı (yalnızca metin, şık görsellik)
        st.markdown(
            f"""
<div style="
    border:1px solid #e5e7eb;
    background:linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
    padding:14px 16px;
    border-radius:14px;
    margin-top:8px;
">
  <div style="display:flex; gap:18px; align-items:center; flex-wrap:wrap;">
    <div style="display:flex; align-items:center; gap:10px;">
      <span style="font-size:22px;">🧷</span>
      <div>
        <div style="font-weight:700; font-size:14px; color:#0f172a;">Yield Strength (0.2% offset)</div>
        <div style="font-weight:600; font-size:16px; color:#111827;">{ys_txt}</div>
      </div>
    </div>
    <div style="height:28px; width:1px; background:#e5e7eb;"></div>
    <div style="display:flex; align-items:center; gap:10px;">
      <span style="font-size:22px;">🏔️</span>
      <div>
        <div style="font-weight:700; font-size:14px; color:#0f172a;">UTS (Ultimate Tensile Strength)</div>
        <div style="font-weight:600; font-size:16px; color:#111827;">{uts_txt}</div>
      </div>
    </div>
    <div style="height:28px; width:1px; background:#e5e7eb;"></div>
    <div style="display:flex; align-items:center; gap:10px;">
      <span style="font-size:22px;">📈</span>
      <div>
        <div style="font-weight:700; font-size:14px; color:#0f172a;">Elongation at Break</div>
        <div style="font-weight:600; font-size:16px; color:#111827;">{eb_txt}</div>
      </div>
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        # PNG olarak indir
        png_buffer = BytesIO()
        fig.savefig(png_buffer, format="png")
        b64_png = base64.b64encode(png_buffer.getvalue()).decode()
        href_png = f'<a href="data:image/png;base64,{b64_png}" download="{name}_plot.png">📥 Download PNG</a>'
        st.markdown(href_png, unsafe_allow_html=True)

        # Excel olarak indir
        excel_buffer = BytesIO()
        df_result.to_excel(excel_buffer, index=False, engine='openpyxl')
        b64_excel = base64.b64encode(excel_buffer.getvalue()).decode()
        href_excel = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="{name}_data.xlsx">📥 Download Excel</a>'
        st.markdown(href_excel, unsafe_allow_html=True)

        # Ortak grafiğe ekle
        combined_ax.plot(df_result["Strain (%)"], df_result["Stress (MPa)"], label=name)
        combined_ax.set_xlim(0, 6)
        combined_ax.set_ylim(0, 80)

    except Exception as e:
        st.error(f"❌ Error in file '{file_info['original_filename']}': {e}")

# 🟦 Combined grafik göster
if selected_names:
    combined_ax.legend()
    st.markdown("### 📈 Combined Stress-Strain Graph")
    st.pyplot(combined_fig)

    combined_png_buf = BytesIO()
    combined_fig.savefig(combined_png_buf, format="png")
    b64_combined = base64.b64encode(combined_png_buf.getvalue()).decode()
    combined_href = f'<a href="data:image/png;base64,{b64_combined}" download="combined_stress_strain.png">📥 Download Combined PNG</a>'
    st.markdown(combined_href, unsafe_allow_html=True)
