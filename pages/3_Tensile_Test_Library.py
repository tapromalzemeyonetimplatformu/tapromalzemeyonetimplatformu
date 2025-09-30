# 3_Tensile_Test_Library.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import StringIO, BytesIO
import os
import base64
from datetime import datetime
import numpy as np
import math

# =========================
# 🔐 Giriş kontrolü
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.set_page_config(page_title="Tensile Test Library", page_icon="🔬", layout="wide")
st.title("Tensile Test Library")

# =========================
# 📂 Klasör & metadata
# =========================
UPLOAD_DIR = "uploaded_tensile_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
metadata_file = os.path.join(UPLOAD_DIR, "metadata.csv")

if os.path.exists(metadata_file):
    df_meta = pd.read_csv(metadata_file)
else:
    df_meta = pd.DataFrame(columns=["stored_filename", "original_filename", "user_given_name", "uploader", "timestamp"])
    df_meta.to_csv(metadata_file, index=False)

# =========================
# 📤 Yükleme alanı
# =========================
st.subheader("📤 Upload a new tensile test file")

uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])
user_given_name = st.text_input("Enter a name for this file")

if "username" not in st.session_state:
    st.session_state.username = "unknown"

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

# =========================
# 📁 Dosya listesi
# =========================
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

# =========================
# ⚙️ Yardımcı hesap fonksiyonları
# =========================
def _as_float_series(x):
    return pd.to_numeric(pd.Series(x), errors="coerce")

def _linear_region_fit(strain_pct, stress_mpa):
    s = _as_float_series(strain_pct).to_numpy()
    y = _as_float_series(stress_mpa).to_numpy()
    mask = np.isfinite(s) & np.isfinite(y)
    s, y = s[mask], y[mask]
    if len(s) < 8:
        return None, None
    # Varsayılan doğrusal bölge: %0.05–%0.5 (yoksa ilk %5 veri)
    lin_mask = (s >= 0.05) & (s <= 0.5)
    if lin_mask.sum() < 8:
        n = max(8, int(len(s)*0.05))
        s_lin, y_lin = s[:n], y[:n]
    else:
        s_lin, y_lin = s[lin_mask], y[lin_mask]
    try:
        m, c = np.polyfit(s_lin, y_lin, 1)
        # Uygunluk (R^2)
        y_hat = m*s_lin + c
        ss_res = np.sum((y_lin - y_hat)**2)
        ss_tot = np.sum((y_lin - np.mean(y_lin))**2)
        r2 = 1 - ss_res/ss_tot if ss_tot > 0 else None
        return (m, c, r2), (s_lin, y_lin)
    except Exception:
        return None, None

def compute_yield_strength_02_offset(strain_pct, stress_mpa, offset_pct=0.2):
    s = _as_float_series(strain_pct).to_numpy()
    y = _as_float_series(stress_mpa).to_numpy()
    mask = np.isfinite(s) & np.isfinite(y)
    s, y = s[mask], y[mask]
    if len(s) < 5:
        return None
    try:
        fit, _ = _linear_region_fit(s, y)
        if fit is None:
            # offset kesişimi yoksa %0.2'deki gerilme
            return float(np.interp(offset_pct, s, y))
        m, c, _ = fit
        y_off = m*(s - offset_pct) + c
        diff = y - y_off
        sign = np.sign(diff)
        changes = np.where(np.diff(sign) != 0)[0]
        if len(changes) == 0:
            return float(np.interp(offset_pct, s, y))
        i = changes[0]
        s1, s2 = s[i], s[i+1]
        d1, d2 = diff[i], diff[i+1]
        s_star = s1 if (d2 - d1) == 0 else s1 - d1*(s2 - s1)/(d2 - d1)
        ys = float(np.interp(s_star, [s1, s2], [y[i], y[i+1]]))
        return ys
    except Exception:
        return None

def compute_elongation_at_break_pct(strain_pct, stress_mpa):
    s = _as_float_series(strain_pct)
    y = _as_float_series(stress_mpa)
    df = pd.DataFrame({"s": s, "y": y}).dropna()
    positive = df[df["y"] > 0]
    if not positive.empty:
        return float(positive["s"].iloc[-1])
    if not df.empty:
        return float(df["s"].iloc[-1])
    return None

def compute_uts_mpa(stress_mpa):
    y = _as_float_series(stress_mpa)
    if y.dropna().empty:
        return None
    return float(y.max())

def noise_metric(stress_mpa):
    """Basit gürültü metriği: 3-nokta hareketli ortalama artıklarının medyan mutlak sapması."""
    y = _as_float_series(stress_mpa).dropna().to_numpy()
    if len(y) < 7:
        return None
    y_smooth = pd.Series(y).rolling(3, center=True).mean().to_numpy()
    mask = np.isfinite(y_smooth)
    res = y[mask] - y_smooth[mask]
    return float(np.median(np.abs(res)))

def anomaly_flags(strain_pct, stress_mpa):
    """Erken akma, negatif eğim, ani sıçrama vb. işaretler"""
    s = _as_float_series(strain_pct).dropna().to_numpy()
    y = _as_float_series(stress_mpa).dropna().to_numpy()
    flags = []
    if len(s) < 10 or len(y) < 10:
        return ["insufficient-data"]
    # Negatif eğim (geniş)
    if np.any(np.diff(y) < -max(1.0, 0.02*np.nanmax(y))):
        flags.append("neg-slope-segments")
    # Ani spike
    if np.any(np.abs(np.diff(y)) > max(2.0, 0.05*np.nanmax(y))):
        flags.append("stress-spike")
    # Erken akma: %0.2 civarı YS çok düşükse
    ys = compute_yield_strength_02_offset(s, y, 0.2)
    uts = compute_uts_mpa(y)
    if ys is not None and uts is not None and ys < 0.25*uts:
        flags.append("early-yield")
    # Kırılma öncesi uzun plato
    y_max = np.nanmax(y)
    if np.sum(y > 0.95*y_max) > max(5, 0.02*len(y)):
        flags.append("long-plateau")
    return flags if flags else ["ok"]

def pct_diff(value, ref):
    if value is None or ref is None or ref == 0:
        return None
    return 100.0*(value - ref)/ref

# =========================
# 🧠 Offline Analyzer (Gemini yoksa)
# =========================
def offline_commentary(stats, user_ranges=None):
    """
    stats: {name: {E, R2, YS, UTS, EB, noise, flags}}
    user_ranges: {"E": (min,max), "YS":(...), "UTS":(...), "EB":(...)} – opsiyonel
    """
    lines = []
    names = list(stats.keys())
    if not names:
        return "No selection."

    # Sıralamalar
    key_order = ["E", "YS", "UTS", "EB"]
    labels = {"E": "Modulus (E)", "YS": "Yield (0.2%)", "UTS": "UTS", "EB": "Elongation at Break"}
    for k in key_order:
        vs = [(n, stats[n].get(k)) for n in names]
        vs = [(n, v) for (n, v) in vs if v is not None]
        if vs:
            vs_sorted = sorted(vs, key=lambda x: x[1], reverse=True)
            top = ", ".join([f"{i+1}. {nm} ({vs_sorted[i][1]:.2f})" for i, (nm, _) in enumerate(vs_sorted[:3])])
            lines.append(f"• {labels[k]} ranking → {top}")

    # Kullanıcı aralıklarına göre sapmalar
    if user_ranges:
        for metric_key, rng in user_ranges.items():
            if rng and all(r is not None for r in rng):
                lo, hi = rng
                bad = []
                for n in names:
                    val = stats[n].get(metric_key)
                    if val is None:
                        continue
                    if val < lo:
                        bad.append(f"{n} ({val:.2f} < {lo:.2f})")
                    elif val > hi:
                        bad.append(f"{n} ({val:.2f} > {hi:.2f})")
                if bad:
                    metric_label = labels.get(metric_key, metric_key)
                    lines.append(f"• Out-of-range {metric_label}: " + "; ".join(bad))

    # Gürültü ve R2 ile veri kalitesi
    poor = [n for n in names if (stats[n].get("R2") is not None and stats[n]["R2"] < 0.95) or (stats[n].get("noise") is not None and stats[n]["noise"] > 2.0)]
    if poor:
        why = []
        for n in poor:
            bits = []
            if stats[n].get("R2") is not None and stats[n]["R2"] < 0.95:
                bits.append(f"low linearity (R²={stats[n]['R2']:.3f})")
            if stats[n].get("noise") is not None and stats[n]["noise"] > 2.0:
                bits.append(f"high noise (≈{stats[n]['noise']:.2f})")
            if bits:
                why.append(f"{n}: " + ", ".join(bits))
        if why:
            lines.append("• Data quality warnings → " + " | ".join(why))

    # Anomali bayrakları
    ann = []
    for n in names:
        fl = stats[n].get("flags", [])
        if fl and fl != ["ok"]:
            ann.append(f"{n}: {', '.join(fl)}")
    if ann:
        lines.append("• Anomaly flags → " + " | ".join(ann))

    # İkili kıyas (en güçlü vs en sünek)
    if len(names) >= 2:
        # En yüksek E ve EB
        best_E = max([(n, stats[n].get("E")) for n in names if stats[n].get("E") is not None], key=lambda x: x[1], default=None)
        best_EB = max([(n, stats[n].get("EB")) for n in names if stats[n].get("EB") is not None], key=lambda x: x[1], default=None)
        if best_E and best_EB:
            lines.append(f"• Stiffest vs ductile → E↑: {best_E[0]} ({best_E[1]:.2f}); EB↑: {best_EB[0]} ({best_EB[1]:.2f} %)")
        # E ile YS uyumu
        pairs = []
        for n in names:
            if stats[n].get("E") is not None and stats[n].get("YS") is not None:
                pairs.append((n, stats[n]["YS"]/max(1e-6, stats[n]["E"])))
        if pairs:
            pairs_sorted = sorted(pairs, key=lambda x: x[1])
            low = pairs_sorted[0]; high = pairs_sorted[-1]
            lines.append(f"• YS/E ratio spread → lowest: {low[0]} ({low[1]:.3f}), highest: {high[0]} ({high[1]:.3f})")

    return "\n".join(lines) if lines else "No notable differences detected."

# =========================
# 🧪 Veri seçimi
# =========================
st.subheader("📊 Choose data to analyze")
selected_names = st.multiselect(
    label="Select one or more uploaded files to visualize",
    options=df_meta["user_given_name"].tolist()
)

# =========================
# 📥 Literatür/Referans Aralıkları (opsiyonel)
# =========================
with st.expander("📚 (Optional) Enter expected literature ranges for numeric deviations"):
    c1, c2, c3, c4 = st.columns(4)
    E_min = c1.number_input("E min (MPa/%strain)", value=0.0, step=0.1)
    E_max = c2.number_input("E max (MPa/%strain)", value=0.0, step=0.1)
    YS_min = c3.number_input("YS min (MPa)", value=0.0, step=0.1)
    YS_max = c4.number_input("YS max (MPa)", value=0.0, step=0.1)
    d1, d2, d3, d4 = st.columns(4)
    UTS_min = d1.number_input("UTS min (MPa)", value=0.0, step=0.1)
    UTS_max = d2.number_input("UTS max (MPa)", value=0.0, step=0.1)
    EB_min = d3.number_input("EB min (%)", value=0.0, step=0.1)
    EB_max = d4.number_input("EB max (%)", value=0.0, step=0.1)

    use_ranges = st.checkbox("Use these ranges to mark deviations", value=False)
    user_ranges = None
    if use_ranges:
        def _rng(a,b):
            return (a,b) if (a>0 or b>0) and (b>=a) else None
        user_ranges = {
            "E": _rng(E_min, E_max),
            "YS": _rng(YS_min, YS_max),
            "UTS": _rng(UTS_min, UTS_max),
            "EB": _rng(EB_min, EB_max),
        }

# =========================
# 📈 Çizimler + Hesaplar
# =========================
combined_fig, combined_ax = plt.subplots()
combined_ax.set_xlabel("Uzama (%)")
combined_ax.set_ylabel("Gerilme (MPa)")

stats = {}  # {name: {E, R2, YS, UTS, EB, noise, flags}}

if selected_names:
    st.markdown("### 🔎 Per-file data & curves")
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

        # Verinin başladığı satır
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

        # Tablo
        st.markdown(f"#### 📄 Data from: *{name}*")
        st.dataframe(df_result)

        # Grafik
        fig, ax = plt.subplots()
        ax.plot(df_result["Strain (%)"], df_result["Stress (MPa)"], label=name)
        ax.set_xlabel("Strain (%)")
        ax.set_ylabel("Stress (MPa)")
        ax.set_title(f"Stress-Strain Curve: {name}")
        st.pyplot(fig)

        # Hesaplar
        fit, (s_lin, y_lin) = _linear_region_fit(df_result["Strain (%)"], df_result["Stress (MPa)"])
        if fit is not None:
            m, c, r2 = fit
            E_est = m  # MPa per %strain (çünkü eksen %)
        else:
            m = c = r2 = None
            E_est = None

        ys = compute_yield_strength_02_offset(df_result["Strain (%)"], df_result["Stress (MPa)"], offset_pct=0.2)
        uts = compute_uts_mpa(df_result["Stress (MPa)"])
        e_break = compute_elongation_at_break_pct(df_result["Strain (%)"], df_result["Stress (MPa)"])
        nm = noise_metric(df_result["Stress (MPa)"])
        fl = anomaly_flags(df_result["Strain (%)"], df_result["Stress (MPa)"])

        stats[name] = {"E": E_est, "R2": r2, "YS": ys, "UTS": uts, "EB": e_break, "noise": nm, "flags": fl}

        # Sonuç kartı
        ys_txt = f"{ys:.2f} MPa" if ys is not None else "—"
        uts_txt = f"{uts:.2f} MPa" if uts is not None else "—"
        eb_txt = f"{e_break:.2f} %" if e_break is not None else "—"
        E_txt = f"{E_est:.2f} (MPa/%strain)" if E_est is not None else "—"
        r2_txt = f"{r2:.3f}" if r2 is not None else "—"
        nm_txt = f"{nm:.2f}" if nm is not None else "—"

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
    <div><b>Modulus (E):</b> {E_txt} &nbsp;|&nbsp; <b>Linear R²:</b> {r2_txt}</div>
    <div style="height:28px; width:1px; background:#e5e7eb;"></div>
    <div><b>Yield (0.2%):</b> {ys_txt} &nbsp;|&nbsp; <b>UTS:</b> {uts_txt} &nbsp;|&nbsp; <b>EB:</b> {eb_txt}</div>
    <div style="height:28px; width:1px; background:#e5e7eb;"></div>
    <div><b>Noise:</b> {nm_txt} &nbsp;|&nbsp; <b>Flags:</b> {", ".join(fl)}</div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        # İndirmeler
        png_buffer = BytesIO()
        fig.savefig(png_buffer, format="png")
        b64_png = base64.b64encode(png_buffer.getvalue()).decode()
        href_png = f'<a href="data:image/png;base64,{b64_png}" download="{name}_plot.png">📥 Download PNG</a>'
        st.markdown(href_png, unsafe_allow_html=True)

        excel_buffer = BytesIO()
        df_result.to_excel(excel_buffer, index=False, engine='openpyxl')
        b64_excel = base64.b64encode(excel_buffer.getvalue()).decode()
        href_excel = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="{name}_data.xlsx">📥 Download Excel</a>'
        st.markdown(href_excel, unsafe_allow_html=True)

        # Combined
        combined_ax.plot(df_result["Strain (%)"], df_result["Stress (MPa)"], label=name)
        combined_ax.set_xlim(0, 6)
        combined_ax.set_ylim(0, 80)

    except Exception as e:
        st.error(f"❌ Error in file '{file_info['original_filename']}': {e}")

# =========================
# 📈 Combined grafik ve kıyas tablosu
# =========================
if selected_names:
    combined_ax.legend()
    st.markdown("### 📈 Combined Stress-Strain Graph")
    st.pyplot(combined_fig)

    combined_png_buf = BytesIO()
    combined_fig.savefig(combined_png_buf, format="png")
    b64_combined = base64.b64encode(combined_png_buf.getvalue()).decode()
    combined_href = f'<a href="data:image/png;base64,{b64_combined}" download="combined_stress_strain.png">📥 Download Combined PNG</a>'
    st.markdown(combined_href, unsafe_allow_html=True)

    # Kıyas tablosu
    rows = []
    for n, d in stats.items():
        rows.append({
            "Name": n,
            "E (MPa/%strain)": None if d.get("E") is None else round(d["E"], 3),
            "Linear R²": None if d.get("R2") is None else round(d["R2"], 4),
            "YS_0.2% (MPa)": None if d.get("YS") is None else round(d["YS"], 3),
            "UTS (MPa)": None if d.get("UTS") is None else round(d["UTS"], 3),
            "EB (%)": None if d.get("EB") is None else round(d["EB"], 3),
            "Noise": None if d.get("noise") is None else round(d["noise"], 3),
            "Flags": ", ".join(d.get("flags", []))
        })
    df_cmp = pd.DataFrame(rows)
    st.markdown("### 🧮 Numeric comparison table")
    st.dataframe(df_cmp, use_container_width=True)

# =========================
# 🤖 AI Commentary (Gemini opsiyonel, Offline varsayılan)
# =========================
if selected_names:
    st.markdown("### 🤖 AI Commentary")

    # 1) Offline nicel yorum
    off_text = offline_commentary(stats, user_ranges=user_ranges)
    st.markdown("**Offline Analyzer (no API key needed)**")
    st.code(off_text, language="markdown")

    # 2) Gemini (opsiyonel) – GOOGLE_API_KEY varsa devreye girer
    use_gemini = st.checkbox("Use Gemini if GOOGLE_API_KEY is available (optional)", value=False)
    if use_gemini:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            st.warning("No GOOGLE_API_KEY found. Offline Analyzer is already active.")
        else:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                # Sayısal özet prompt
                prompt = [
                    "You are a materials testing assistant. Produce concise, strictly quantitative commentary.",
                    "Metrics available per curve: E (MPa per %strain), linear R^2, YS_0.2% (MPa), UTS (MPa), EB (%), noise, flags.",
                    "Provide: (1) rankings per metric, (2) out-of-range items vs user ranges if given, (3) data-quality warnings using R^2 and noise, (4) anomalies, (5) 1–2 line takeaway.",
                    f"User ranges: {user_ranges}",
                    f"Stats dict: {stats}"
                ]
                resp = model.generate_content("\n".join([str(p) for p in prompt]))
                txt = resp.text if hasattr(resp, "text") else str(resp)
                st.markdown("**Gemini (optional)**")
                st.code(txt, language="markdown")
            except Exception as e:
                st.error(f"Gemini call failed, falling back to Offline Analyzer. Details: {e}")
