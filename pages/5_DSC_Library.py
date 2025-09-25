# pages/5_DSC_Library.py
import io, hashlib, re, math
from datetime import datetime
from typing import Dict, Tuple, List, Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ----------------------------- #
# ---------- Helpers ---------- #
# ----------------------------- #

def sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1(); h.update(b); return h.hexdigest()

HEADER_KEYS = {
    "size": re.compile(r"^Size\s+([\d\.\-]+)\s*mg", re.I),
    "sig1": re.compile(r"^Sig1\s*:\s*(.+)", re.I),
    "sig2": re.compile(r"^Sig2\s*:\s*(.+)", re.I),
    "sig3": re.compile(r"^Sig3\s*:\s*(.+)", re.I),
    "heatflow_mode": re.compile(r"^SelHeatFlow\s*[:\s]\s*(.+)", re.I),
    "temprange": re.compile(r"^TempRange\s*([^\n]+)", re.I),
    "orgmethod_ramp": re.compile(r"^OrgMethod\s*.*?:\s*Ramp\s*([\d\.]+)\s*°C/min", re.I),
    "date": re.compile(r"^Date\s*([\d\-]+)", re.I),
}

def parse_ta_txt(file_bytes: bytes) -> Tuple[pd.DataFrame, Dict[str,str]]:
    """
    Parse TA Instruments DSC text (Q2000) -> DataFrame with Time(min), Temp(°C), HeatFlow(mW)
    Returns (df, meta)
    """
    text = file_bytes.decode(errors="ignore")
    lines = text.strip().splitlines()

    meta = {}
    numeric_lines_start = None
    for i, ln in enumerate(lines):
        ln = ln.strip()
        # collect meta
        for k, rx in HEADER_KEYS.items():
            m = rx.match(ln)
            if m:
                if k == "temprange":
                    meta["TempRange_raw"] = m.group(1).strip()
                elif k == "orgmethod_ramp":
                    meta.setdefault("ramps", []).append(float(m.group(1)))
                elif k == "size":
                    meta["Size_mg"] = float(m.group(1))
                elif k in ("sig1","sig2","sig3","heatflow_mode","date"):
                    meta[k] = m.group(1).strip()
        # detect numeric start: three columns numeric (Time, Temp, HeatFlow)
        # TA txt genellikle sayfa sonu form feed ile "
" sonra üç sütun gelir
        if re.match(r"^[\.\d\-\+Ee]+\s+[\.\d\-\+Ee]+\s+[\.\d\-\+Ee]+$", ln):
            numeric_lines_start = i
            break

    if numeric_lines_start is None:
        # bazı dosyalarda ilk data satırında başta " .0054..." gibi nokta ile başlayabilir
        for i, ln in enumerate(lines):
            if re.match(r"^\s*\.?[\d\-\+Ee]+\s+[\.\d\-\+Ee]+\s+[\.\d\-\+Ee]+$", ln):
                numeric_lines_start = i; break

    # read numeric block
    data = []
    for ln in lines[numeric_lines_start:]:
        ln = ln.strip().replace("\t"," ")
        # bazı satırlar başta '.' ile başlıyor; önüne 0 ekleyelim
        ln = re.sub(r"(^|\s)\.(\d)", r"\g<1>0.\2", ln)
        parts = ln.split()
        if len(parts) != 3: 
            continue
        try:
            t = float(parts[0]); T = float(parts[1]); q = float(parts[2])
            data.append((t, T, q))
        except:
            continue

    df = pd.DataFrame(data, columns=["Time (min)", "Temperature (°C)", "Heat Flow (mW)"])

    # HeatFlow unit & mode
    hf_label = meta.get("sig3","")
    mode_label = meta.get("heatflow_mode","")
    if "(W/g)" in hf_label or "W/g" in mode_label:
        meta["hf_is_wpg"] = True
    else:
        meta["hf_is_wpg"] = False

    # Heating rate
    beta = None
    if meta.get("ramps"):
        # çoğu dosya: 10.00 °C/min
        beta = float(np.median(meta["ramps"]))
    else:
        # TempRange ... at 19.94 °C/min Heat/Cool
        tr = meta.get("TempRange_raw","")
        m = re.search(r"at\s*([\d\.]+)\s*°C/min", tr)
        if m: beta = float(m.group(1))
    if beta is None:
        # veriden tahmin: global medyan dT/dt (°C/min)
        t = df["Time (min)"].values
        T = df["Temperature (°C)"].values
        dTdt = np.gradient(T, t)
        beta = float(np.nanmedian(np.abs(dTdt)))
    meta["beta_C_per_min"] = beta
    meta["beta_K_per_s"] = beta/60.0

    # sample mass
    meta["sample_mg"] = float(meta.get("Size_mg", np.nan))
    meta["sample_g"] = meta["sample_mg"]/1000.0 if not math.isnan(meta["sample_mg"]) else np.nan

    return df, meta

def segment_cycles(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Detect 1st heating, cooling, 2nd heating by sign of dT/dt."""
    T = df["Temperature (°C)"].values
    t = df["Time (min)"].values
    dTdt = np.gradient(T, t)
    sign = np.sign(dTdt)
    # smooth sign
    from scipy.signal import medfilt
    sign_s = medfilt(sign, kernel_size=51)
    # find indices where sign changes
    idx = np.where(np.diff(np.sign(sign_s)) != 0)[0] + 1
    # Expect: [end of H1], [end of Cooling], then H2
    # Robust fallback: split into 3 nearly equal chunks if detection fails
    if len(idx) >= 2:
        i1, i2 = idx[0], idx[1]
    else:
        n = len(df)
        i1, i2 = n//3, 2*n//3
    segs = {
        "heating1": df.iloc[:i1].reset_index(drop=True),
        "cooling": df.iloc[i1:i2].reset_index(drop=True),
        "heating2": df.iloc[i2:].reset_index(drop=True),
    }
    return segs

def to_W_per_g(series_mW: pd.Series, meta: Dict) -> pd.Series:
    # If already W/g -> just ensure units
    if meta.get("hf_is_wpg"):
        # bazı Q2000 konfiglerinde "Sig3: Heat Flow (mW)" yazsa bile SelHeatFlow "W/g" olabilir;
        # yine de kontrol üstte yapıldı.
        return series_mW.astype(float)  # actually W/g
    # mW -> W
    W = series_mW.astype(float) / 1000.0
    # divide by mass to get W/g
    m_g = meta.get("sample_g", np.nan)
    if not m_g or np.isnan(m_g) or m_g == 0:
        return pd.Series(np.nan, index=series_mW.index)
    return W / m_g

def baseline_area_J_per_g(T: np.ndarray, q_wpg: np.ndarray, beta_K_per_s: float,
                          tmin: float, tmax: float, peak: str) -> Tuple[float, float, float]:
    """
    Linear baseline between endpoints; integrate (q_wpg - baseline) / beta dT -> J/g
    peak: 'endo' (ΔHm) or 'exo' (ΔHc/ΔHcc) -> işaret konvansiyonu için.
    """
    mask = (T >= tmin) & (T <= tmax)
    if mask.sum() < 5: 
        return float("nan"), float("nan"), float("nan")
    x = T[mask]; y = q_wpg[mask]
    # baseline
    y0, y1 = y[0], y[-1]
    b = y0 + (y1 - y0) * (x - x[0]) / (x[-1] - x[0])
    yc = y - b
    # enthalpy
    Jg = np.trapz(yc / beta_K_per_s, x)
    # for endo peaks we want positive ΔHm; exo negative area should produce positive ΔHc
    if peak == "exo":
        Jg = -Jg
    return Jg, x[np.argmax(yc if peak=="endo" else -yc)], float(np.max(yc if peak=="endo" else -yc))

def auto_window_from_peak(x: np.ndarray, y: np.ndarray, peak_kind: str) -> Tuple[float,float]:
    """
    Peak based windowing by prominence (robust, library-agnostic).
    """
    from scipy.signal import find_peaks
    if peak_kind=="endo":
        peaks, props = find_peaks(y, prominence=np.nanstd(y))
    else:
        peaks, props = find_peaks(-y, prominence=np.nanstd(y))
    if len(peaks)==0:
        return float(x.min()), float(x.max())
    i = peaks[np.argmax(props["prominences"])]
    # left/right bases from peak properties if available
    left = float(x[max(0, i- int(0.07*len(x)))])
    right = float(x[min(len(x)-1, i+ int(0.07*len(x)))])
    return left, right

REF_WINDOWS = {
    # fallback pencereleri (DSC References'a göre pratik aralıklar)
    "PEEK":   {"melt": (295, 360), "cool": (200, 270), "hcc": (180, 260)},
    "PEKK":   {"melt": (280, 360), "cool": (180, 300), "hcc": (160, 260)},
    "ULTEM":  {"melt": None,       "cool": None,       "hcc": None},  # çoğunlukla amorf: erime yok
}

def compute_results(df: pd.DataFrame, meta: Dict, material: str) -> Dict[str, Optional[float]]:
    segs = segment_cycles(df)
    beta = meta["beta_K_per_s"]
    # convert to W/g
    for k, seg in segs.items():
        seg["Heat Flow (W/g)"] = to_W_per_g(seg["Heat Flow (mW)"], meta)
    res = {"Tg": None, "Tm": None, "Tc": None, "dHm": None, "dHc": None, "dHcc": None, "Xc": None}

    # --- Tg from 2nd heating (inflection of baseline-corrected curve around step)
    h2 = segs["heating2"]
    T2 = h2["Temperature (°C)"].to_numpy()
    q2 = h2["Heat Flow (W/g)"].to_numpy()
    # find step via max of derivative of smoothed q2
    from scipy.ndimage import gaussian_filter1d
    q2s = gaussian_filter1d(q2, 11)
    dq2 = np.gradient(q2s, T2)
    # choose Tg where |dq2| maximum in broad 80–220°C window (genel)
    mask_tg = (T2>80) & (T2<220)
    if mask_tg.sum()>10:
        Tg = float(T2[mask_tg][np.argmin(dq2[mask_tg])])  # endotherm up→down genellikle negatif eğim
        res["Tg"] = round(Tg, 2)

    # --- ΔHm & Tm from 2nd heating
    # auto or fallback windows
    material_u = (material or "").upper().strip()
    win_ref = REF_WINDOWS.get(material_u, REF_WINDOWS["PEEK"])
    if win_ref.get("melt"):
        wmin, wmax = win_ref["melt"]
    else:
        wmin, wmax = 250, 380
    # refine windows by peak detection
    wmask = (T2>=wmin)&(T2<=wmax)
    if wmask.sum()>20:
        awmin, awmax = auto_window_from_peak(T2[wmask], q2[wmask], "endo")
        wmin, wmax = max(wmin, awmin), min(wmax, awmax)
    dHm, Tm, _ = baseline_area_J_per_g(T2, q2, beta, wmin, wmax, peak="endo")
    res["dHm"] = round(dHm, 2) if np.isfinite(dHm) else None
    res["Tm"]  = round(Tm, 2) if np.isfinite(Tm)  else None

    # --- Tc & ΔHc from cooling (exo)
    c = segs["cooling"]; Tc=None
    TcT = c["Temperature (°C)"].to_numpy()
    cq = c["Heat Flow (W/g)"].to_numpy()
    if win_ref.get("cool"):
        cmin, cmax = win_ref["cool"]
    else:
        cmin, cmax = 180, 320
    cmask = (TcT>=cmin)&(TcT<=cmax)
    if cmask.sum()>20:
        awmin, awmax = auto_window_from_peak(TcT[cmask], cq[cmask], "exo")
        cmin, cmax = max(cmin, awmin), min(cmax, awmax)
    dHc, Tc, _ = baseline_area_J_per_g(TcT, cq, beta, cmin, cmax, peak="exo")
    res["dHc"] = round(dHc, 2) if np.isfinite(dHc) else None
    res["Tc"]  = round(Tc, 2)  if np.isfinite(Tc)  else None

    # --- ΔHcc from 1st heating (exo; cold crystallization)
    h1 = segs["heating1"]
    T1 = h1["Temperature (°C)"].to_numpy()
    q1 = h1["Heat Flow (W/g)"].to_numpy()
    if win_ref.get("hcc"):
        kmin, kmax = win_ref["hcc"]
    else:
        kmin, kmax = 150, 270
    kmask = (T1>=kmin)&(T1<=kmax)
    if kmask.sum()>20:
        awmin, awmax = auto_window_from_peak(T1[kmask], q1[kmask], "exo")
        kmin, kmax = max(kmin, awmin), min(kmax, awmax)
    dHcc, _, _ = baseline_area_J_per_g(T1, q1, beta, kmin, kmax, peak="exo")
    res["dHcc"] = round(dHcc, 2) if np.isfinite(dHcc) else None

    # --- Crystallinity
    # ΔH° referans (J/g) – DSC References
    DH0 = 130.0  # (PEEK/PEKK ortak varsayılan; gerektiğinde materyale özel değiştirilebilir)
    polymer_fraction = 1.00
    if res["dHm"] is not None:
        Xc = (res["dHm"] - (res["dHcc"] or 0.0)) / (DH0 * polymer_fraction) * 100.0
        res["Xc"] = round(Xc, 2)
    return res

def plot_curve(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    # beyaz arka plan, okunaklı renk
    fig.update_layout(template="plotly_white", title=title,
                      xaxis_title="Temperature (°C)", yaxis_title="Heat Flow (mW)")
    fig.add_trace(go.Scatter(
        x=df["Temperature (°C)"], y=df["Heat Flow (mW)"],
        mode="lines", name="Heat Flow", line=dict(width=2)
    ))
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    return fig

# ----------------------------- #
# ------------ UI ------------- #
# ----------------------------- #

st.set_page_config(page_title="DSC Library", layout="wide")

# Session state
st.session_state.setdefault("library", {})   # key: sha1, value: dict(meta)
st.session_state.setdefault("staged", [])    # list of (sha1, bytes)

st.title("DSC Library")

with st.container(border=True):
    st.subheader("Upload DSC .txt files")
    user_name = st.text_input("User Name / Custom Tag", value="", placeholder="örn. PEEK-CF-XY-1.txt")
    uploaded = st.file_uploader("Drag and drop files here", type=["txt"], accept_multiple_files=True, key="dsc_uploader")
    colA, colB = st.columns([1,1])
    with colA:
        if st.button("Stage files", use_container_width=True, disabled=not uploaded):
            staged = []
            for f in uploaded or []:
                b = f.read()
                h = sha1_bytes(b)
                staged.append((h, b, f.name))
            st.session_state["staged"] = staged
            st.success(f"{len(staged)} file(s) staged. Name them below, then add to library.")
    with colB:
        if st.button("Clear staged", use_container_width=True):
            st.session_state["staged"] = []

    if st.session_state["staged"]:
        for h, b, fname in st.session_state["staged"]:
            default_label = user_name if user_name else fname
            new_label = st.text_input("Label", value=default_label, key=f"label_{h}")
            add = st.button("Add to library", key=f"add_{h}")
            if add:
                if h in st.session_state["library"]:
                    st.info("Already in library – skipped.")
                else:
                    # parse once and store lightweight meta; raw bytes da lazım
                    df, meta = parse_ta_txt(b)
                    st.session_state["library"][h] = {
                        "label": new_label, "filename": fname,
                        "bytes": b, "meta": meta
                    }
                    st.success(f"Added: {new_label}")

# Library list
st.subheader("Uploaded DSC Files")
if st.session_state["library"]:
    for h, rec in st.session_state["library"].items():
        cols = st.columns([3,3,2,2,1])
        cols[0].markdown(f"**{rec['filename']}**")
        cols[1].text_input("User Name", value=rec["label"], key=f"nm_{h}", disabled=True)
        meta = rec["meta"]
        dt = meta.get("date","")
        cols[2].write(dt)
        if cols[4].button("Delete", key=f"del_{h}"):
            st.session_state["library"].pop(h, None)
            st.experimental_rerun()

# ----------------------------- #
# --------- Analyzer ---------- #
# ----------------------------- #

st.subheader("Select a file to analyze")

options = [(rec["label"], h) for h, rec in st.session_state["library"].items()]
selected_key = st.selectbox("Choose a file", options=[o[1] for o in options], format_func=lambda k: dict(options)[k] if options else "", index=0 if options else None)

col1, col2, col3 = st.columns([1,1,1])
material = col1.selectbox("Material", ["PEEK","PEKK","ULTEM","Other"], index=0)
dtype = col2.selectbox("Type", ["Type III"], index=0)
operator = col3.text_input("Operator", value="")

if selected_key:
    rec = st.session_state["library"][selected_key]
    df, meta = parse_ta_txt(rec["bytes"])

    # top stats
    c1, c2, c3 = st.columns(3)
    c1.metric("Sample Mass (mg)", f"{meta.get('sample_mg', float('nan')):.3f}")
    c2.metric("Heating Rate (°C/min)", f"{meta.get('beta_C_per_min', float('nan')):.2f}")
    c3.metric("Operator", operator if operator else "—")

    # raw data table + download
    st.markdown("### Raw Data")
    st.dataframe(df.head(500), use_container_width=True)
    st.download_button("Download raw data (CSV)", data=df.to_csv(index=False).encode(), file_name=f"{rec['label']}_raw.csv", mime="text/csv")

    # curve
    st.markdown("### DSC Curve with Analysis")
    fig = plot_curve(df, title=rec["label"])
    st.plotly_chart(fig, use_container_width=True, config={"toImageButtonOptions":{"format":"png","filename":f"{rec['label']}_curve"}})

    # calculations
    st.markdown("### Calculated Results (Type III)")
    res = compute_results(df, meta, material)
    tbl = pd.DataFrame(
        [[res["Tg"], res["Tm"], res["Tc"], res["dHm"], res["dHcc"], res["dHc"], res["Xc"]]],
        columns=["Tg (°C)","Tm (°C)","Tc (°C)","ΔHm (J/g)","ΔHcc (J/g)","ΔHc (J/g)","Crystallinity Xc (%)"]
    )
    st.table(tbl)

    # short summary
    summary = (f"Tg = {res['Tg']}; Tm = {res['Tm']}; Tc = {res['Tc']}; "
               f"ΔHm = {res['dHm']}; ΔHcc = {res['dHcc']}; ΔHc = {res['dHc']}; "
               f"Crystallinity Xc (%) = {res['Xc']}.")
    st.info(summary)

    # footnote
    beta_txt = f"β = {meta['beta_C_per_min']:.2f} °C/min ({meta['beta_K_per_s']:.4f} K/s)."
    mode_txt = "Heat Flow mode = W/g" if meta.get("hf_is_wpg") else "Heat Flow mode = mW → W/g dönüştürüldü."
    st.caption(beta_txt + " " + mode_txt + " Hesap: tek satır kuralı (2. ısıtma: Tg/Tm/ΔHm; soğutma: Tc/ΔHc; 1. ısıtma: ΔHcc). "
               "Entegral: baseline-düzeltmeli ∫(q_W/g / β) dT. Referans ΔH°=130 J/g, polymer fraction=1.00. "
               "Pencereler: tepe bulma ile otomatik, bulunamazsa malzeme referans aralıklarına düşer.")

else:
    st.info("Önce bir dosya ekleyip listeden seçin.")

