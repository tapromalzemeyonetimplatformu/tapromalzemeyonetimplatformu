import streamlit as st
import pandas as pd
import os
import datetime
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter, find_peaks
import io
import re
from collections import Counter

# ================================
# 0) Auth kontrolü
# ================================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.set_page_config(page_title="DSC Library", page_icon="🔬", layout="wide")
st.title("DSC Library")

current_user = st.session_state.get("username", "unknown")

# ================================
# 1) Klasör/metadata
# ================================
UPLOAD_DIR = "dsc_uploads"
META_FILE = "dsc_uploads_metadata.csv"
os.makedirs(UPLOAD_DIR, exist_ok=True)

META_COLUMNS = ["file_name", "custom_name", "uploaded_by", "upload_time"]
if os.path.exists(META_FILE):
    meta_df = pd.read_csv(META_FILE)
    for col in META_COLUMNS:
        if col not in meta_df.columns:
            meta_df[col] = ""
    meta_df = meta_df[META_COLUMNS]
else:
    meta_df = pd.DataFrame(columns=META_COLUMNS)

# ================================
# 2) Dosya yükleme
# ================================
st.subheader("📤 Upload DSC Raw Data")
uploaded_file = st.file_uploader("Upload your DSC .txt file", type=["txt"])
custom_name = st.text_input("Custom name for this file")

if uploaded_file is not None and st.button("Save Upload", type="primary"):
    save_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    new_entry = {
        "file_name": uploaded_file.name,
        "custom_name": (custom_name.strip() if custom_name else uploaded_file.name),
        "uploaded_by": current_user,
        "upload_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_df = pd.concat([meta_df, pd.DataFrame([new_entry])], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.success(f"✅ File '{uploaded_file.name}' uploaded and saved.")
    st.rerun()

# ================================
# 3) Yüklenenler listesi
# ================================
st.subheader("📂 Uploaded DSC Files")
if meta_df.empty:
    st.info("No files uploaded yet.")
else:
    hdr = st.columns([5, 5, 4, 2])
    hdr[0].markdown("**File Name**")
    hdr[1].markdown("**Custom Name**")
    hdr[2].markdown("**Upload Time**")
    hdr[3].markdown("**Delete**")
    for _, row in meta_df.reset_index(drop=True).iterrows():
        c = st.columns([5, 5, 4, 2])
        c[0].write(row["file_name"])
        c[1].write(row["custom_name"])
        c[2].write(row["upload_time"])
        if c[3].button("🗑️ Delete", key=f"del_{row['file_name']}"):
            try:
                os.remove(os.path.join(UPLOAD_DIR, row["file_name"]))
            except:
                pass
            meta_df = meta_df.loc[meta_df["file_name"] != row["file_name"]].reset_index(drop=True)
            meta_df.to_csv(META_FILE, index=False)
            st.success(f"Deleted: {row['file_name']}")
            st.rerun()

# ================================
# 4) Yardımcılar
# ================================
def split_header_and_data_lines(path):
    """Başlık satırları ile veri satırlarını ayırır. İlk '3 sayı' görülen satırdan sonrası veridir."""
    with open(path, "r", encoding="latin1") as f:
        lines = f.readlines()
    data_start = None
    for i, ln in enumerate(lines):
        parts = ln.strip().split()
        if len(parts) >= 3:
            try:
                float(parts[0]); float(parts[1]); float(parts[2])
                data_start = i
                break
            except:
                pass
    if data_start is None:
        data_start = len(lines)
    header_lines = lines[:data_start]
    data_lines = lines[data_start:]
    return header_lines, data_lines

def parse_header_for_params(header_lines):
    """
    Header'dan:
      - Sample mass (mg)  -> 'Size <value> mg'
      - Heating rate (°C/min) -> 'TempRange ... at <value> °C/min' veya 'Ramp <value> °C/min ...'
      - Exotherm orientation ('Exotherm UP/DOWN')
    Döndürür: mass_mg (float|None), rate_C_per_min (float|None), exo_up (bool|None)
    """
    mass_mg = None
    rate_vals = []
    exo_up = None

    for ln in header_lines:
        # Mass
        m = re.search(r"\bSize\s+([\-+]?\d+(?:\.\d+)?(?:[Ee][\-+]?\d+)?)", ln)
        if m and mass_mg is None:
            try:
                mass_mg = float(m.group(1))
            except:
                pass
        # Heating rate (TempRange ... at XX °C/min)
        r1 = re.search(r"at\s+([0-9]+(?:\.[0-9]+)?)\s*°C/min", ln, flags=re.IGNORECASE)
        if r1:
            try:
                rate_vals.append(float(r1.group(1)))
            except:
                pass
        # Heating rate (OrgMethod: Ramp XX °C/min ...)
        r2 = re.search(r"Ramp\s+([0-9]+(?:\.[0-9]+)?)\s*°C/min", ln, flags=re.IGNORECASE)
        if r2:
            try:
                rate_vals.append(float(r2.group(1)))
            except:
                pass
        # Exotherm orientation
        if "Exotherm" in ln:
            if "UP" in ln.upper():
                exo_up = True
            elif "DOWN" in ln.upper():
                exo_up = False

    rate_C_per_min = None
    if rate_vals:
        # Çoğunluk değerini al (ör. 20.0 tekrar eder)
        rate_C_per_min = Counter(np.round(rate_vals, 2)).most_common(1)[0][0]

    return mass_mg, rate_C_per_min, exo_up

def load_dsc_data_from_lines(data_lines):
    """Veri satırlarından DataFrame üretir."""
    data = []
    for line in data_lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            try:
                tmin = float(parts[0])
                temp = float(parts[1])
                hf = float(parts[2])
                data.append([tmin, temp, hf])
            except:
                continue
    return pd.DataFrame(data, columns=["Time (min)", "Temperature (°C)", "Heat Flow (mW)"])

def estimate_rate_from_data(df):
    """Header yoksa ilk 5-10% bölgeden T vs time lineer fit ile °C/min tahmin et."""
    if df.empty:
        return None
    n = max(50, int(len(df) * 0.1))
    sub = df.iloc[:n]
    try:
        # slope = dT/dt (°C/min)
        p = np.polyfit(sub["Time (min)"].values, sub["Temperature (°C)"].values, 1)
        return float(p[0])
    except:
        return None

def segment_cycles(df, slope_threshold=0.5):
    """
    dT/dt işaretine göre Heating/Cooling segmentleri ayır.
    slope_threshold: °C/min altında kalanlar isothermal sayılır ve komşuya yapıştırılır.
    Dönen liste: [{"name": "Heating 1", "mask": mask}, {"name": "Cooling", ...}, {"name":"Heating 2", ...}]
    """
    if df.empty:
        return []

    t = df["Time (min)"].values
    T = df["Temperature (°C)"].values

    # dT/dt (°C/min)
    dTdt = np.gradient(T, t)
    sign = np.where(dTdt > slope_threshold, 1, np.where(dTdt < -slope_threshold, -1, 0))

    # Isothermal (0) bölgelerini komşu yönlerle doldur
    # Basit yaklaşım: soldan-sağa ve sağdan-sola doldurma
    filled = sign.copy()
    last = 0
    for i in range(len(filled)):
        if filled[i] == 0:
            filled[i] = last
        else:
            last = filled[i]
    last = 0
    for i in range(len(filled)-1, -1, -1):
        if filled[i] == 0:
            filled[i] = last
        else:
            last = filled[i]

    # Grupla
    segments = []
    start = 0
    for i in range(1, len(filled)):
        if filled[i] != filled[i-1]:
            segments.append((filled[start], start, i))
            start = i
    segments.append((filled[start], start, len(filled)))

    # Sadece +1 (Heating) ve -1 (Cooling) olanları al
    hc = [(sgn, s, e) for (sgn, s, e) in segments if sgn in (-1, 1) and (e - s) > 10]

    ordered = []
    names = []
    for sgn, s, e in hc:
        nm = "Heating" if sgn == 1 else "Cooling"
        names.append(nm)
        mask = np.zeros(len(df), dtype=bool)
        mask[s:e] = True
        ordered.append({"name": nm, "mask": mask})

    # İlk Heating → Heating 1, sonra Cooling, sonra Heating 2 olarak adlandır
    heating_indices = [i for i, seg in enumerate(ordered) if seg["name"] == "Heating"]
    cooling_indices = [i for i, seg in enumerate(ordered) if seg["name"] == "Cooling"]

    final = []
    if heating_indices:
        final.append({"name": "Heating 1", "mask": ordered[heating_indices[0]]["mask"]})
    if cooling_indices:
        final.append({"name": "Cooling", "mask": ordered[cooling_indices[0]]["mask"]})
    if len(heating_indices) > 1:
        final.append({"name": "Heating 2", "mask": ordered[heating_indices[1]]["mask"]})

    return final

# ΔH°fus referansları (J/g)
DHfus_ref = {"PEKK": 130.0, "PEEK": 130.0, "PPS": 79.0, "PESU": None}

# Entegrasyon pencereleri (°C)
TABLE_RANGES = {
    "Tg":  (80, 200),
    "Tc":  (200, 360),
    "Tm":  (330, 420),
    "ΔHcc": (80, 330),   # Type III & Heating 1
    "ΔHc":  (200, 360),  # Cooling
    "ΔHf":  (330, 420),  # Melting
}

def integrate_J_per_g(T, hf_mW, mask, rate_C_per_min, mass_mg):
    """
    ∫(mW) dT / β / m  → mJ/g; 1e-3 ile J/g
    β = °C/s = (°C/min)/60
    """
    if rate_C_per_min is None or mass_mg is None or mass_mg <= 0:
        return np.nan
    beta = rate_C_per_min / 60.0
    if np.sum(mask) < 2:
        return np.nan
    area_mW_dT = np.trapz(hf_mW[mask], T[mask])  # mW * °C
    mJ_per_g = area_mW_dT / beta / (mass_mg / 1000.0)  # mJ/g
    return mJ_per_g * 1e-3  # J/g

def compute_events_on_segment(seg_name, T, hf_s, rate_C_per_min, mass_mg, material, exo_up=True):
    """
    Bir segment (Heating 1 / Cooling / Heating 2) için Tg, Tc, Tm ve entalpileri hesaplar.
    """
    res = {
        "name": seg_name,
        "Tg": np.nan, "Tc": np.nan, "Tm": np.nan,
        "ΔHcc": np.nan, "ΔHc": np.nan, "ΔHm": np.nan,
        "Crystallinity": np.nan
    }

    # Segment penceresi
    rng_T = (np.nanmin(T), np.nanmax(T))
    def within(segment_range):
        lo, hi = segment_range
        return (T >= lo) & (T <= hi)

    # ---------------- Tg (genellikle Heating'de)
    if seg_name.startswith("Heating"):
        lo, hi = TABLE_RANGES["Tg"]
        mask_tg = within((max(lo, rng_T[0]), min(hi, rng_T[1])))
        if np.sum(mask_tg) > 3:
            try:
                dHdT = np.gradient(hf_s[mask_tg], T[mask_tg])
                idx = np.argmax(np.abs(dHdT))
                Tg_val = T[mask_tg][idx]
                if lo <= Tg_val <= hi:
                    res["Tg"] = float(Tg_val)
            except:
                pass

    # ---------------- Tc (Cooling)
    if seg_name == "Cooling":
        lo, hi = TABLE_RANGES["Tc"]
        mask_tc = within((max(lo, rng_T[0]), min(hi, rng_T[1])))
        if np.sum(mask_tc) > 3:
            try:
                # Exotherm UP ise Tc tepe (pozitif), DOWN ise tepe (-hf_s)
                peaks_tc, _ = find_peaks(hf_s[mask_tc] if exo_up else -hf_s[mask_tc], prominence=0.01, distance=50)
                if len(peaks_tc) > 0:
                    res["Tc"] = float(T[mask_tc][peaks_tc[0]])
                # ΔHc
                res["ΔHc"] = integrate_J_per_g(T, hf_s, mask_tc, rate_C_per_min, mass_mg)
            except:
                pass

    # ---------------- Tm ve ΔHm (Heating)
    if seg_name.startswith("Heating"):
        lo, hi = TABLE_RANGES["Tm"]
        mask_tm = within((max(lo, rng_T[0]), min(hi, rng_T[1])))
        if np.sum(mask_tm) > 3:
            try:
                # Melting endo: Exotherm UP konv. ile çukur; DOWN ise tepe
                y_for_peaks = -hf_s[mask_tm] if exo_up else hf_s[mask_tm]
                peaks_tm, _ = find_peaks(y_for_peaks, prominence=0.01, distance=50)
                if len(peaks_tm) > 0:
                    res["Tm"] = float(T[mask_tm][peaks_tm[0]])
                # ΔHm (J/g)
                # Exotherm UP'ta erime entalpisi pozitif raporlanır diye çevirmiyoruz;
                # işaret veri işaretine göre doğal çıkıyor, kullanıcı yorumu için aynen bırakıyoruz.
                val = integrate_J_per_g(T, hf_s, mask_tm, rate_C_per_min, mass_mg)
                # Erime genelde endo olduğundan J/g değeri pozitif görünmesi beklenir;
                # eğer negatif gelirse mutlak almayı tercih edebilirsiniz.
                res["ΔHm"] = val
            except:
                pass

    # ---------------- ΔHcc (sadece Type III & Heating 1)
    if seg_name == "Heating 1":
        lo, hi = TABLE_RANGES["ΔHcc"]
        mask_cc = within((max(lo, rng_T[0]), min(hi, rng_T[1])))
        if np.sum(mask_cc) > 3:
            try:
                res["ΔHcc"] = integrate_J_per_g(T, hf_s, mask_cc, rate_C_per_min, mass_mg)
            except:
                pass

    # ---------------- Kristallenme %
    DH_ref = DHfus_ref.get(material, None)
    if DH_ref and not np.isnan(DH_ref):
        # Type III kuralı: (ΔHm − ΔHcc) / ΔH° * 100
        dHm = res["ΔHm"] if not np.isnan(res["ΔHm"]) else 0.0
        dHcc = res["ΔHcc"] if not np.isnan(res["ΔHcc"]) else 0.0
        res["Crystallinity"] = (dHm - dHcc) / DH_ref * 100.0

    return res

def fmt(v, unit=""):
    try:
        if v is None or np.isnan(v):
            return "—"
    except:
        pass
    return f"{float(v):.2f} {unit}".strip()

# ================================
# 5) Analiz
# ================================
if not meta_df.empty:
    st.markdown("---")
    st.subheader("🔎 Analyze a File")

    selected_custom = st.selectbox("Select a file to analyze", meta_df["custom_name"].tolist())
    row = meta_df.loc[meta_df["custom_name"] == selected_custom].iloc[0]
    file_path = os.path.join(UPLOAD_DIR, row["file_name"])
    if not os.path.exists(file_path):
        st.error("File missing on disk.")
        st.stop()

    # ---- Header & Data Parse ----
    header_lines, data_lines = split_header_and_data_lines(file_path)
    mass_mg, rate_C_per_min, exo_up = parse_header_for_params(header_lines)
    df = load_dsc_data_from_lines(data_lines)

    if df.empty:
        st.error("No numeric data found in the file.")
        st.stop()

    # Yedek: oran tahmini
    if rate_C_per_min is None:
        rate_C_per_min = estimate_rate_from_data(df)

    # ---- Otomatik bilgileri göster ----
    top = st.columns(4)
    top[0].metric("Type", "III")  # sabit
    material = top[1].selectbox("Material", ["PEKK", "PEEK", "PPS", "PESU"])
    top[2].metric("Sample Mass", fmt(mass_mg, "mg"))
    top[3].metric("Heating Rate", fmt(rate_C_per_min, "°C/min"))

    # ---- Raw data + download ----
    st.markdown("**📋 Raw Data**")
    st.dataframe(df, use_container_width=True)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="DSC Raw Data")
    st.download_button(
        "⬇️ Download Raw Data (.xlsx)",
        data=excel_buffer.getvalue(),
        file_name=f"{row['custom_name']}_raw.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ---- Smoothing ----
    T_all = df["Temperature (°C)"].values
    HF = df["Heat Flow (mW)"].values
    win = 101 if len(HF) >= 101 else max(3, (len(HF)//2)*2+1)
    HF_s = savgol_filter(HF, window_length=win, polyorder=3)

    # ---- Segmentasyon ----
    segments = segment_cycles(df)

    # Eğer segment bulunamazsa en azından tüm eğriyi Heating 1 gibi ele al
    if not segments:
        mask_all = np.ones(len(df), dtype=bool)
        segments = [{"name": "Heating 1", "mask": mask_all}]

    # ---- Her segment için hesaplamalar ----
    results = []
    for seg in segments:
        mask = seg["mask"]
        T_seg = T_all[mask]
        HF_seg = HF_s[mask]
        res = compute_events_on_segment(
            seg["name"], T_seg, HF_seg, rate_C_per_min, mass_mg, material, exo_up=True if exo_up is None else exo_up
        )
        results.append(res)

    # ================================
    # 6) Grafik (işaretlemeli)
    # ================================
    st.subheader("📊 DSC Curve with Analysis")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(T_all, HF, color="gray", alpha=0.35, label="Raw")
    ax.plot(T_all, HF_s, label="Smoothed")

    # Segment arkaplanları
    colors_bg = {"Heating 1": (0.0, 0.5, 1.0, 0.06), "Cooling": (0.0, 1.0, 0.4, 0.06), "Heating 2": (1.0, 0.4, 0.2, 0.06)}
    for seg in segments:
        mask = seg["mask"]
        if np.any(mask):
            ax.axvspan(T_all[mask][0], T_all[mask][-1], color=colors_bg.get(seg["name"], (0,0,0,0.03)), label=seg["name"])

    # Olay çizgileri
    for res in results:
        if not np.isnan(res["Tg"]):
            ax.axvline(res["Tg"], color="orange", linestyle="--", linewidth=1.2, label=f"Tg ({res['name']})")
        if not np.isnan(res["Tc"]):
            ax.axvline(res["Tc"], color="green", linestyle="--", linewidth=1.2, label=f"Tc ({res['name']})")
        if not np.isnan(res["Tm"]):
            ax.axvline(res["Tm"], color="red", linestyle="--", linewidth=1.2, label=f"Tm ({res['name']})")

    # Pencere gölgelendirmeleri (tüm eğri üzerinde göster)
    lo_tc, hi_tc = TABLE_RANGES["Tc"]
    ax.fill_between(T_all, HF_s, 0, where=((T_all >= lo_tc) & (T_all <= hi_tc)), color="green", alpha=0.10, label="Tc window")
    lo_tm, hi_tm = TABLE_RANGES["Tm"]
    ax.fill_between(T_all, HF_s, 0, where=((T_all >= lo_tm) & (T_all <= hi_tm)), color="red", alpha=0.10, label="Tm window")
    lo_cc, hi_cc = TABLE_RANGES["ΔHcc"]
    ax.fill_between(T_all, HF_s, 0, where=((T_all >= lo_cc) & (T_all <= hi_cc)), color="purple", alpha=0.08, label="ΔHcc window")

    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Heat Flow (mW)")
    ax.legend(loc="best", ncol=2)
    ax.grid(True)

    png_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=300, bbox_inches="tight")
    st.download_button(
        "⬇️ Download DSC Curve with Analysis (.png)",
        data=png_buf.getvalue(),
        file_name=f"{row['custom_name']}_curve_analysis.png",
        mime="image/png"
    )
    st.pyplot(fig)

    # ================================
    # 7) Sonuç kartları
    # ================================
    st.subheader("Calculated Results (Type III)")

    # Kartları 3 sütun halinde yazalım
    def card(title, value, subtitle=""):
        st.markdown(
            f"""
<div style="border:1px solid #e5e7eb; border-radius:12px; padding:12px 14px; background:linear-gradient(180deg,#fff,#fafafa); margin-bottom:8px;">
  <div style="font-size:13px; color:#475569; font-weight:600;">{title}</div>
  <div style="font-size:18px; font-weight:700; color:#111827;">{value}</div>
  {"<div style='font-size:12px; color:#6b7280;'>" + subtitle + "</div>" if subtitle else ""}
</div>
""",
            unsafe_allow_html=True
        )

    # Segment bazlı gösterim
    for res in results:
        st.markdown(f"#### {res['name']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Tg (°C)", fmt(res["Tg"], "°C"))
        if res["name"] == "Cooling":
            c2.metric("Tc (°C)", fmt(res["Tc"], "°C"))
        else:
            c2.metric("Tm (°C)", fmt(res["Tm"], "°C"))
        c3.metric("ΔHm (J/g)", fmt(res["ΔHm"], "J/g"))

        c4, c5, c6 = st.columns(3)
        # ΔHcc sadece Heating 1'de hesaplanır
        c4.metric("ΔHcc (J/g)", fmt(res["ΔHcc"], "J/g") if res["name"] == "Heating 1" else "—")
        c5.metric("ΔHc (J/g)", fmt(res["ΔHc"], "J/g") if res["name"] == "Cooling" else "—")
        c6.metric("Crystallinity (%)", fmt(res["Crystallinity"], "%"))

    st.info("ℹ️ Enthalpy integrals are reported in J/g (unit-corrected).")

# ================================
# 8) Standard Report (Single-Set)
# ================================
st.markdown("---")
st.subheader("Report Format — Type III Convention")

# Segmentlere kolay erişim
seg = {r["name"]: r for r in results}
h1 = seg.get("Heating 1")
cool = seg.get("Cooling")
h2 = seg.get("Heating 2")

def _get(seg_obj, key):
    if seg_obj is None:
        return np.nan
    val = seg_obj.get(key, np.nan)
    try:
        return float(val) if not np.isnan(val) else np.nan
    except Exception:
        return np.nan

# Type III raporlama seçimleri
tg_val   = _get(h2 if h2 is not None else h1, "Tg")
tm_val   = _get(h2 if h2 is not None else h1, "Tm")
tc_val   = _get(cool, "Tc")
dhm_val  = _get(h2 if h2 is not None else h1, "ΔHm")
# ΔHcc ikinci ısıtmada yoksa (genelde yoktur) 1. ısıtmadan al
dhcc_2nd = _get(h2, "ΔHcc")
dhcc_1st = _get(h1, "ΔHcc")
dhcc_val = dhcc_2nd if not np.isnan(dhcc_2nd) else dhcc_1st

# Kristallenme (%) = (ΔHm − ΔHcc) / ΔH°_fus × 100
DH_ref = DHfus_ref.get(material)
if DH_ref is None or np.isnan(DH_ref) or np.isnan(dhm_val):
    xc_val = np.nan
else:
    _dhcc = 0.0 if np.isnan(dhcc_val) else dhcc_val
    xc_val = (dhm_val - _dhcc) / DH_ref * 100.0

# Üst bilgi
top_cols = st.columns(4)
top_cols[0].metric("Type", "III")
top_cols[1].metric("Material", material)
top_cols[2].metric("Sample Mass", fmt(mass_mg, "mg"))
top_cols[3].metric("Heating Rate", fmt(rate_C_per_min, "°C/min"))

# Özet kartı (tekil değerler)
st.markdown(
    f"""
<div style="border:1px solid #e5e7eb; border-radius:14px; padding:16px; background:linear-gradient(180deg,#ffffff,#fafafa);">
  <div style="display:flex; gap:22px; flex-wrap:wrap;">
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">Tg (2nd heat)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(tg_val, "°C")}</div>
    </div>
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">Tm (2nd heat)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(tm_val, "°C")}</div>
    </div>
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">Tc (cooling)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(tc_val, "°C")}</div>
    </div>
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">ΔHm (2nd heat)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(dhm_val, "J/g")}</div>
    </div>
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">ΔHcc (pref. 2nd → else 1st)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(dhcc_val, "J/g")}</div>
    </div>
    <div>
      <div style="font-size:13px;color:#475569;font-weight:700;">Crystallinity (Xc)</div>
      <div style="font-size:18px;font-weight:800;color:#111827;">{fmt(xc_val, "%")}</div>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# İndirme için tabloya dök
summary_df = pd.DataFrame(
    [{
        "Type": "III",
        "Material": material,
        "Sample Mass (mg)": None if mass_mg is None else round(float(mass_mg), 4),
        "Heating Rate (°C/min)": None if rate_C_per_min is None else round(float(rate_C_per_min), 4),
        "Tg (°C)": None if np.isnan(tg_val) else round(tg_val, 2),
        "Tm (°C)": None if np.isnan(tm_val) else round(tm_val, 2),
        "Tc (°C)": None if np.isnan(tc_val) else round(tc_val, 2),
        "ΔHm (J/g)": None if np.isnan(dhm_val) else round(dhm_val, 3),
        "ΔHcc (J/g)": None if np.isnan(dhcc_val) else round(dhcc_val, 3),
        "Xc (%)": None if np.isnan(xc_val) else round(xc_val, 2),
        "ΔH°fus ref (J/g)": DH_ref if DH_ref is not None else None,
    }]
)

st.markdown("**Report Table**")
st.dataframe(summary_df, use_container_width=True)

