# 5_DSC_Library.py  —  DSC Library (revised)
# ⬇️ Kopyala-yapıştır çalışır. Upload/Files/Select/Type/Material/SampleMass/RawData/Download kısımları korunmuştur.
# Değişiklikler:
# - Heating Rate başlıktan doğru çekilir (OrgMethod: Ramp X.XX C/min).
# - Grafik sade: yalnızca eğri, indirilebilir.
# - Sonuçlar tek blok: Tg, Tm, ΔHm, ΔHcc, ΔHc, %Crystallinity (doğru çevrim kuralları ile).
# - ΔH° varsayılanları: PEEK/PEKK=130 J/g; PPS=112 J/g (UI’dan override edilebilir).
# - Filler düzeltmesi için polymer mass fraction input’u (vars. 1.00).

import io, re, math
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# --- Page config (ilk çağrı) ---
st.set_page_config(page_title="DSC Library", page_icon="🔥", layout="wide")

# -------------- Utilities --------------

HEADER_DECODING = {
    "sample": ["Sample", "Sample Name"],
    "size_mg": ["Size", "Sample mass", "Mass", "Weight"],
    "pan_mass": ["PanMass", "Pan mass"],
    "operator": ["Operator"],
    "instrument": ["Instrument"],
    "orgmethod": ["OrgMethod", "Method", "Program"],
    "file": ["File", "OrgFile"],
    "mode": ["Mode"],
    "language": ["Language"],
    "run": ["Run"]
}

POLYMER_DH0_DEFAULTS = {
    # Varsayılan ΔH° [J/g] (100% kristal)
    "PEEK": 130.0,   # literature common
    "PEKK": 130.0,   # literature common
    "PPS": 112.0     # common reported; editable in UI
}

def parse_header_and_data(txt: str):
    """TA formatındaki .txt dosyadan header + tabloyu ayıkla."""
    lines = txt.splitlines()
    # Header sonu: ilk sayısal satır
    num_re = re.compile(r'^\s*[-+]?(\d+\.?\d*|\.\d+)([Ee][-+]?\d+)?')
    start_idx = None
    for i, l in enumerate(lines):
        if num_re.match(l.strip()):
            start_idx = i
            break
    header = lines[:start_idx] if start_idx is not None else []
    data_str = "\n".join(lines[start_idx:]) if start_idx is not None else ""

    # Header alanlarını yakala
    H = {}
    for k, keys in HEADER_DECODING.items():
        for key in keys:
            for ln in header:
                if ln.startswith(key + "\t") or ln.startswith(key + " "):
                    parts = re.split(r"\t|\s{2,}", ln.strip())
                    if len(parts) >= 2:
                        H[k] = parts[1]
                        break
            if k in H: break

    # Sample mass (mg) — "Size\t3.35400\tmg" gibi
    sample_mass_mg = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_DECODING["size_mg"]):
            # satır içinde mg sayısını yakala
            m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*mg', ln)
            if m:
                sample_mass_mg = float(m.group(1))
                break

    # Heating rate: OrgMethod satırlarında "Ramp 10.00 C/min ..."
    heating_rate_c_min = None
    org_lines = [ln for ln in header if any(ln.strip().startswith(kw) for kw in HEADER_DECODING["orgmethod"])]
    # İlk "Ramp a to b" pozitif eğimli komut ısıtma hızıdır (C/min)
    for ln in org_lines:
        # ör: "OrgMethod 3: Ramp 10.00 C/min to 400.00 C"
        m = re.search(r'Ramp\s+([0-9]+(?:\.[0-9]+)?)\s*C\s*/\s*min', ln, flags=re.I)
        if m:
            heating_rate_c_min = float(m.group(1))
            break

    # Veri: 3 kolon (Time, Temp, HeatFlow) — whitespace ayrımlı
    if data_str.strip():
        df = pd.read_csv(io.StringIO(data_str), delim_whitespace=True, header=None, names=["Time", "Temp", "HeatFlow"], engine="python")
    else:
        df = pd.DataFrame(columns=["Time","Temp","HeatFlow"])

    meta = {
        "sample_name": H.get("sample", ""),
        "sample_mass_mg": sample_mass_mg,
        "operator": H.get("operator", ""),
        "instrument": H.get("instrument", ""),
        "file": H.get("file", ""),
        "heating_rate_c_min": heating_rate_c_min
    }
    return meta, df

def split_cycles(df: pd.DataFrame):
    """
    Sıcaklık trendine göre segmentleri ayır: Heating1 -> Cooling -> Heating2
    """
    if df.empty or len(df) < 20:
        return df.copy(), pd.DataFrame(), pd.DataFrame()

    T = df["Temp"].to_numpy()
    dT = np.gradient(T)
    # Bölümleme: dT>0 heating, dT<0 cooling
    # İlk pozitif uzun segment -> H1, sonra negatif -> C, sonra tekrar pozitif -> H2
    sign = np.sign(dT)
    # yumuşatma: tekil sapmaları bastır
    from scipy.ndimage import uniform_filter1d
    sign_s = uniform_filter1d(sign, size=51, mode='nearest')
    idxs = np.arange(len(df))

    # geçiş noktaları
    trans = np.where(np.diff(np.signbit(sign_s)))[0] + 1
    # Basit mantık: başı (+) ise H1 başlar; sonra (-) -> C; sonra (+) -> H2
    # Aşırı bölünmeleri önlemek için en uzun üç bloğu seç
    blocks = []
    last = 0
    for t in list(trans) + [len(df)]:
        blocks.append((last, t))
        last = t
    # Her blok için ortalama dT işareti
    labeled = []
    for a,b in blocks:
        if b-a < 50: continue
        s = np.sign(np.mean(dT[a:b]))
        labeled.append((a,b,int(s)))
    # (+) -> H, (-) -> C
    heats = [blk for blk in labeled if blk[2] >= 0]
    cools = [blk for blk in labeled if blk[2] < 0]
    # H1 = ilk heat bloğu
    H1 = heats[0] if heats else None
    # C = H1'den sonra gelen ilk cool
    C = None
    if H1:
        for blk in cools:
            if blk[0] > H1[1]:
                C = blk
                break
    # H2 = C'den sonra gelen ilk heat
    H2 = None
    if C:
        for blk in heats:
            if blk[0] > C[1]:
                H2 = blk
                break

    def slice_blk(blk):
        return df.iloc[blk[0]:blk[1]].reset_index(drop=True) if blk else pd.DataFrame(columns=df.columns)

    return slice_blk(H1), slice_blk(C), slice_blk(H2)

def linear_baseline_integral(T, Y, tmin, tmax):
    """[J/g] için alan: Y=W/g, x=°C. Lineer baseline ile ∫(Y - baseline) dT."""
    mask = (T>=tmin) & (T<=tmax)
    if not np.any(mask):
        return np.nan
    Tseg = T[mask]; Yseg = Y[mask]
    # Bas çizgi: uç noktalardan geçen doğru
    y0 = Yseg[0]; y1 = Yseg[-1]
    x0 = Tseg[0]; x1 = Tseg[-1]
    baseline = y0 + (y1-y0)*(Tseg-x0)/(x1-x0+1e-12)
    corr = Yseg - baseline
    # Trapez
    area = np.trapz(corr, Tseg)
    return float(area)

def peak_max(T, Y, tmin=None, tmax=None):
    m = np.ones_like(T, dtype=bool)
    if tmin is not None: m &= (T>=tmin)
    if tmax is not None: m &= (T<=tmax)
    if not np.any(m): return np.nan
    idx = np.nanargmax(Y[m])
    # global index
    idx_global = np.arange(len(Y))[m][idx]
    return float(T[idx_global])

def peak_min(T, Y, tmin=None, tmax=None):
    m = np.ones_like(T, dtype=bool)
    if tmin is not None: m &= (T>=tmin)
    if tmax is not None: m &= (T<=tmax)
    if not np.any(m): return np.nan
    idx = np.nanargmin(Y[m])
    idx_global = np.arange(len(Y))[m][idx]
    return float(T[idx_global])

def tg_inflection(T, Y, tmin=None, tmax=None):
    """Tg: inflection (dY/dT maksimum) — sade yaklaşım."""
    m = np.ones_like(T, dtype=bool)
    if tmin is not None: m &= (T>=tmin)
    if tmax is not None: m &= (T<=tmax)
    if not np.any(m): return np.nan
    Tm = T[m]; Ym = Y[m]
    # hafif yumuşatma
    from scipy.ndimage import gaussian_filter1d
    Ys = gaussian_filter1d(Ym, sigma=7)
    dY = np.gradient(Ys, Tm)
    idx = np.nanargmax(np.abs(dY))  # step güçlü ise |dY| max
    return float(Tm[idx])

def choose_intervals(material_key: str):
    """
    Malzemeye göre kaba aralık önerileri (gerekirse UIdan override).
    Type III kurallarına uygun defaultlar: 
      - ΔHm: 2. ısıtma,
      - ΔHc: soğuma,
      - ΔHcc: 1. ısıtma (varsa).
    Not: Sınırlar gerekirse geniş tutuldu. Kullanıcı değiştirebilir.
    """
    # Geniş default sınırlar (°C) — gerektiğinde UI’dan daraltılabilir.
    if material_key.upper().startswith("PEEK"):
        return {"tg": (120, 170), "hm": (300, 380), "hc": (180, 280), "hcc": (150, 260)}
    if material_key.upper().startswith("PEKK"):
        return {"tg": (130, 170), "hm": (290, 380), "hc": (160, 270), "hcc": (150, 260)}
    if material_key.upper().startswith("PPS"):
        return {"tg": (70, 110),  "hm": (240, 300), "hc": (150, 220), "hcc": (None, None)}
    # generic
    return {"tg": (50, 200), "hm": (150, 400), "hc": (80, 300), "hcc": (None, None)}

def compute_results_TypeIII(material: str, df_all: pd.DataFrame, H1: pd.DataFrame, C: pd.DataFrame, H2: pd.DataFrame,
                            dh0: float, polymer_mass_fraction: float, user_intervals: dict):
    """
    Type III kuralları:
      - Tg: 1. veya 2. ısıtma kullanılabilir; pratikte 2. ısıtma daha nettir. Burada H2’den alıyoruz.
      - Tm, ΔHm: 2. ısıtma (H2)
      - Tc, ΔHc: Soğuma (C)
      - ΔHcc: 1. ısıtma (H1), varsa
    """
    # Intervals
    Tg_lo, Tg_hi = user_intervals["tg"]
    Hm_lo, Hm_hi = user_intervals["hm"]
    Hc_lo, Hc_hi = user_intervals["hc"]
    Hcc_lo, Hcc_hi = user_intervals["hcc"]

    # Arrays
    def arr(df):
        return df["Temp"].to_numpy(), df["HeatFlow"].to_numpy()

    # Defaults
    Tg = np.nan; Tm = np.nan; Tc = np.nan
    dHm = np.nan; dHc = np.nan; dHcc = 0.0  # Hcc yoksa 0 kabul
    # Tg: H2’den (daha tekrarlanabilir)
    if not H2.empty:
        T2,Y2 = arr(H2)
        Tg = tg_inflection(T2, Y2, Tg_lo, Tg_hi)
        # ΔHm ve Tm
        Tm = peak_max(T2, Y2, Hm_lo, Hm_hi)
        dHm = linear_baseline_integral(T2, Y2, Hm_lo, Hm_hi)
    # Tc ve ΔHc: cooling
    if not C.empty:
        Tc = peak_min(C["Temp"].to_numpy(), C["HeatFlow"].to_numpy(), Hc_lo, Hc_hi)
        dHc = linear_baseline_integral(C["Temp"].to_numpy(), C["HeatFlow"].to_numpy(), Hc_lo, Hc_hi)
        # Exotherm negatif olabilir → mutlakla
        if not math.isnan(dHc) and dHc > 0:
            dHc = -abs(dHc)
    # ΔHcc: H1’de (varsa)
    if not H1.empty and Hcc_lo is not None and Hcc_hi is not None:
        T1,Y1 = arr(H1)
        # Soğuk kristallenme pikini 1. ısıtmada min arayarak yakala (çoğunlukla ekzotermik)
        dHcc_val = linear_baseline_integral(T1, Y1, Hcc_lo, Hcc_hi)
        if not math.isnan(dHcc_val):
            dHcc = dHcc_val  # genelde negatif gelir → formülde "-" ile kullanılacak

    # Kristalinlik: Xc = ((ΔHm - |ΔHcc|) / (ΔH° * polymer_mass_fraction)) * 100
    # ΔHc raporlanır (isteğe bağlı), Xc hesabında kullanılmaz (klasik yaklaşım).
    corr = dHm - abs(dHcc if not math.isnan(dHcc) else 0.0)
    denom = dh0 * max(polymer_mass_fraction, 1e-6)
    Xc = (corr / denom) * 100.0 if (not math.isnan(corr) and denom>0) else np.nan

    return {
        "Tg (°C)": None if math.isnan(Tg) else round(Tg, 2),
        "Tm (°C)": None if math.isnan(Tm) else round(Tm, 2),
        "Tc (°C)": None if math.isnan(Tc) else round(Tc, 2),
        "ΔHm (J/g)": None if math.isnan(dHm) else round(dHm, 2),
        "ΔHcc (J/g)": None if math.isnan(dHcc) else round(dHcc, 2),
        "ΔHc (J/g)": None if math.isnan(dHc) else round(dHc, 2),
        "Crystallinity Xc (%)": None if math.isnan(Xc) else round(Xc, 2),
        "_cycle_notes": "Tg/Tm/ΔHm from 2nd heating; Tc/ΔHc from cooling; ΔHcc from 1st heating (if present)."
    }

# -------------- Sidebar / Controls --------------

st.title("DSC Library")

# (Korumalı) Upload alanı
st.header("Upload")
uploaded_files = st.file_uploader("Upload DSC .txt files", type=["txt"], accept_multiple_files=True)

# Basit kalıcı liste (oturumluk). Mevcut uygulamadaki mantığı koruyoruz.
if "dsc_files" not in st.session_state:
    st.session_state["dsc_files"] = {}

# Yeni yüklenenleri ekle
if uploaded_files:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for i, f in enumerate(uploaded_files):
        key = f"{f.name}__{ts}_{i}"  # benzersiz anahtar
        st.session_state["dsc_files"][key] = {"name": f.name, "content": f.getvalue()}

st.header("Uploaded DSC Files")
if not st.session_state["dsc_files"]:
    st.info("No files uploaded yet.")
else:
    df_list = pd.DataFrame([{"Key":k, "Filename":v["name"]} for k,v in st.session_state["dsc_files"].items()])
    st.dataframe(df_list, use_container_width=True)

# Type ve Material (korundu)
st.header("Select a file to analyze")
colA, colB = st.columns([2,1])
with colA:
    file_key = st.selectbox("Choose a file", options=list(st.session_state["dsc_files"].keys()) if st.session_state["dsc_files"] else [])
with colB:
    dsc_type = st.selectbox("Type", options=["Type III", "Type II", "Type I"], index=0)
material = st.selectbox("Material", options=["PEEK", "PEKK", "PPS", "OTHER"], index=0)

# ΔH° override ve filler düzeltmesi
with st.expander("Advanced (ΔH° and polymer fraction)"):
    default_dh0 = POLYMER_DH0_DEFAULTS.get(material, 130.0)
    dh0 = st.number_input("ΔH° (J/g) for 100% crystalline polymer", value=float(default_dh0), step=1.0, format="%.2f",
                          help="Literature defaults: PEEK=130, PEKK=130, PPS=112 J/g. Adjust if needed.")
    polymer_fraction = st.number_input("Polymer mass fraction (1 - filler wt. fraction)", min_value=0.0, max_value=1.0, value=1.0, step=0.05)

# -------------- Analysis --------------

if file_key:
    raw = st.session_state["dsc_files"][file_key]["content"].decode("utf-8", errors="ignore")
    meta, df = parse_header_and_data(raw)

    # Baş bilgiler (sample mass & heating rate dosyadan)
    sm_col, hr_col, op_col = st.columns(3)
    with sm_col:
        st.metric("Sample Mass (mg)", f"{meta.get('sample_mass_mg') or '—'}")
    with hr_col:
        hr = meta.get("heating_rate_c_min")
        st.metric("Heating Rate (°C/min)", f"{hr if hr is not None else '—'}")
    with op_col:
        st.metric("Operator", meta.get("operator") or "—")

    # Raw Data (korundu) + download
    st.subheader("Raw Data")
    st.dataframe(df, use_container_width=True, height=300)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download raw data (CSV)", csv, file_name=f"{meta.get('sample_name','sample')}_raw.csv", mime="text/csv")

    # Eğrileri ayır
    H1, C, H2 = split_cycles(df)

    # Grafik — sade ve indirilebilir (modebar toImage açık)
    st.subheader("DSC Curve with Analysis")
    fig = go.Figure()
    def add_trace(D, name):
        if not D.empty:
            fig.add_trace(go.Scatter(x=D["Temp"], y=D["HeatFlow"], mode="lines", name=name))
    add_trace(H1, "Heating 1")
    add_trace(C,  "Cooling")
    add_trace(H2, "Heating 2")
    if H1.empty and C.empty and H2.empty:
        # tek seri ise tüm veriyi çiz
        fig.add_trace(go.Scatter(x=df["Temp"], y=df["HeatFlow"], mode="lines", name="DSC"))
    fig.update_layout(xaxis_title="Temperature (°C)", yaxis_title="Heat Flow (W/g)", legend_title="Segment")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "toImageButtonOptions": {"format": "png"}})

    # Sonuçlar — tek blok (Type III varsayılan)
    st.subheader("Calculated Results (Type III)")
    # Malzemeye göre önerilen aralıklar (UI’dan isteğe göre expose edilebilir)
    suggested = choose_intervals(material)
    results = compute_results_TypeIII(material, df, H1, C, H2, dh0=float(dh0), polymer_mass_fraction=float(polymer_fraction), user_intervals=suggested)

    # Sade tablo
    show = {k:v for k,v in results.items() if not k.startswith("_")}
    res_df = pd.DataFrame(show, index=["Result"])
    st.dataframe(res_df, use_container_width=True)

    # Kısa özet metni (kafa karıştırmayan)
    lines = []
    if show.get("Tg (°C)") is not None: lines.append(f"Tg = {show['Tg (°C)']} °C")
    if show.get("Tm (°C)") is not None: lines.append(f"Tm = {show['Tm (°C)']} °C")
    if show.get("Tc (°C)") is not None: lines.append(f"Tc = {show['Tc (°C)']} °C")
    if show.get("ΔHm (J/g)") is not None: lines.append(f"ΔHm = {show['ΔHm (J/g)']} J/g")
    if show.get("ΔHcc (J/g)") is not None: lines.append(f"ΔHcc = {show['ΔHcc (J/g)']} J/g")
    if show.get("ΔHc (J/g)") is not None: lines.append(f"ΔHc = {show['ΔHc (J/g)']} J/g")
    if show.get("Crystallinity Xc (%)") is not None: lines.append(f"Xc = {show['Crystallinity Xc (%)']} %")
    summary = "; ".join(lines) if lines else "No calculable result in the selected ranges."
    st.info(summary)

    # Mini not: hangi çevrimler kullanıldı + düzeltmeler
    st.caption(f"{results.get('_cycle_notes','')}  ΔH°={dh0:.1f} J/g; polymer fraction={polymer_fraction:.2f}.")
else:
    st.info("Select a file to analyze.")
