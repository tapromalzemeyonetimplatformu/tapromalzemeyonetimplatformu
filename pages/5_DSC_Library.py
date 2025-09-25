# 5_DSC_Library.py  --  DSC Library (stable)

import io
import re
import math
import hashlib
from datetime import datetime
from typing import Tuple, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ---------------- Basic setup ----------------
st.set_page_config(page_title="DSC Library", page_icon="🔥", layout="wide")

def safe_rerun():
    try:
        st.rerun()
    except Exception:
        pass

# ---------------- Parse TA txt ----------------
HDR = {
    "size_mg": re.compile(r"^Size\s+([0-9.+-]+)\s*mg", re.I),
    "org_ramp": re.compile(r"^OrgMethod.*?Ramp\s*([0-9.+-]+)\s*°?C/?min", re.I),
    "temprange": re.compile(r"^TempRange.*?at\s*([0-9.+-]+)\s*°?C/?min", re.I),
    "sig3": re.compile(r"^Sig3\s*:\s*(.+)", re.I),
    "hfmode": re.compile(r"^SelHeatFlow\s*:\s*(.+)", re.I),
    "date": re.compile(r"^Date\s*(.+)", re.I),
}

def parse_ta_txt(b: bytes) -> Tuple[pd.DataFrame, Dict]:
    text = b.decode(errors="ignore")
    lines = text.splitlines()
    meta = {}
    data_start = None

    for i, ln in enumerate(lines):
        s = ln.strip()
        # header capture
        m = HDR["size_mg"].match(s)
        if m: meta["size_mg"] = float(m.group(1))
        m = HDR["org_ramp"].match(s)
        if m: meta.setdefault("ramps", []).append(float(m.group(1)))
        m = HDR["temprange"].match(s)
        if m: meta["tramp"] = float(m.group(1))
        m = HDR["sig3"].match(s)
        if m: meta["sig3"] = m.group(1)
        m = HDR["hfmode"].match(s)
        if m: meta["hfmode"] = m.group(1)
        m = HDR["date"].match(s)
        if m: meta["date"] = m.group(1)

        # first numeric line (3 columns)
        if data_start is None and re.match(r"^[\s.+-Ee0-9]+\s+[\s.+-Ee0-9]+\s+[\s.+-Ee0-9]+$", s):
            data_start = i

    if data_start is None:
        # fallback
        for i, ln in enumerate(lines):
            if re.match(r"^\s*\.?[0-9Ee+-]+\s+\.?[0-9Ee+-]+\s+\.?[0-9Ee+-]+\s*$", ln):
                data_start = i
                break

    rows = []
    for ln in lines[data_start:]:
        s = re.sub(r"(^|\s)\.(\d)", r"\g<1>0.\2", ln.strip())
        parts = s.split()
        if len(parts) != 3:
            continue
        try:
            t = float(parts[0]); T = float(parts[1]); q = float(parts[2])
            rows.append((t, T, q))
        except:
            continue

    df = pd.DataFrame(rows, columns=["Time (min)", "Temperature (C)", "Heat Flow (raw)"])

    # heating rate
    beta = None
    if meta.get("ramps"):
        beta = float(np.median(meta["ramps"]))
    elif meta.get("tramp"):
        beta = float(meta["tramp"])
    else:
        t = df["Time (min)"].values
        T = df["Temperature (C)"].values
        if len(t) > 5:
            dTdt = np.gradient(T, t)
            beta = float(np.nanmedian(np.abs(dTdt)))
    meta["beta_C_per_min"] = beta if beta else np.nan
    meta["beta_C_per_s"] = (beta/60.0) if beta else np.nan

    # mass
    mg = meta.get("size_mg", np.nan)
    meta["mass_mg"] = mg
    meta["mass_g"] = (mg/1000.0) if (mg and not math.isnan(mg)) else np.nan

    # unit hint
    hf_lbl = (meta.get("sig3") or "") + " " + (meta.get("hfmode") or "")
    meta["raw_is_wpg_hint"] = ("W/g" in hf_lbl)

    return df, meta

# ---------------- Segmentation ----------------
def split_cycles(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    T = df["Temperature (C)"].to_numpy()
    t = df["Time (min)"].to_numpy()
    if len(T) < 50:
        n = len(T)
        return df.iloc[:n//3], df.iloc[n//3:2*n//3], df.iloc[2*n//3:]

    dTdt = np.gradient(T, t)
    # median filter for robustness
    from scipy.signal import medfilt
    s = medfilt(np.sign(dTdt), kernel_size=51)
    cuts = np.where(np.diff(s) != 0)[0] + 1
    if len(cuts) >= 2:
        i1, i2 = cuts[0], cuts[1]
    else:
        n = len(T); i1, i2 = n//3, 2*n//3
    return (
        df.iloc[:i1].reset_index(drop=True),
        df.iloc[i1:i2].reset_index(drop=True),
        df.iloc[i2:].reset_index(drop=True),
    )

# ---------------- Unit handling ----------------
def raw_to_Wpg(raw: np.ndarray, mass_g: float, mode: str) -> np.ndarray:
    if mode == "wpg":
        return raw.astype(float)
    # mode == "mw" : raw assumed mW
    return (raw.astype(float) / 1000.0) / mass_g

def choose_unit_auto(H2: pd.DataFrame, mass_g: float, beta_C_per_s: float,
                     melt_window: Tuple[float, float]) -> str:
    if mass_g is None or mass_g <= 0 or np.isnan(mass_g) or H2.empty or not beta_C_per_s:
        return "mw"
    T = H2["Temperature (C)"].to_numpy()
    qraw = H2["Heat Flow (raw)"].to_numpy()
    a, b = melt_window
    # try both
    def area(mode):
        Y = raw_to_Wpg(qraw, mass_g, mode)
        return melt_area_local(T, Y, beta_C_per_s, a, b)
    d1 = abs(area("mw"))
    d2 = abs(area("wpg"))
    # score
    def score(d):
        if 5 <= d <= 150: return abs(80 - d) * 0.01
        if 1 <= d <= 200: return abs(80 - d) * 0.05
        return abs(d - 80) * 0.5 + 100
    return "mw" if score(d1) <= score(d2) else "wpg"

# ---------------- Windows ----------------
REF = {
    "PEEK":  {"tg": (120,170), "melt": (300,385), "cool": (180,280), "hcc": (150,260)},
    "PEKK":  {"tg": (150,170), "melt": (295,360), "cool": (200,270), "hcc": (180,260)},
    "ULTEM": {"tg": (180,230), "melt": (None,None), "cool": (None,None), "hcc": (None,None)},
    "OTHER": {"tg": (50,200),  "melt": (150,400), "cool": (80,300),  "hcc": (120,300)},
}

def ranges_for(material: str) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    key = (material or "").upper()
    return REF.get(key, REF["OTHER"])

# ---------------- Baseline & areas ----------------
def local_baseline(x: np.ndarray, y: np.ndarray, pk_idx: int,
                   pad: float = 10.0, side: float = 6.0) -> np.ndarray:
    """
    Build local linear baseline using two small strips:
      left: [pk - pad - side, pk - pad]
      right: [pk + pad, pk + pad + side]
    """
    xl = x[(x >= x[pk_idx] - pad - side) & (x <= x[pk_idx] - pad)]
    xr = x[(x >= x[pk_idx] + pad) & (x <= x[pk_idx] + pad + side)]
    yl = y[(x >= x[pk_idx] - pad - side) & (x <= x[pk_idx] - pad)]
    yr = y[(x >= x[pk_idx] + pad) & (x <= x[pk_idx] + pad + side)]
    if len(xl) < 3 or len(xr) < 3:
        # fallback to simple endpoints
        x0, x1 = x[0], x[-1]
        y0, y1 = y[0], y[-1]
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0 + 1e-12)
    xl_m, yl_m = np.mean(xl), np.mean(yl)
    xr_m, yr_m = np.mean(xr), np.mean(yr)
    return yl_m + (yr_m - yl_m) * (x - xl_m) / (xr_m - xl_m + 1e-12)

def melt_area_local(T: np.ndarray, Y: np.ndarray, beta_C_per_s: float,
                    a: float, b: float) -> float:
    m = (T >= a) & (T <= b)
    if not np.any(m) or not beta_C_per_s:
        return np.nan
    x = T[m]; y = Y[m]
    # pick peak (endo -> maximum for W/g positive endotherm, TA sign conv may vary)
    pk = int(np.nanargmax(y))
    base = local_baseline(x, y, pk_idx=pk, pad=10.0, side=6.0)
    area = np.trapz((y - base) / beta_C_per_s, x)  # J/g
    return abs(float(area))

def exo_area_local(T: np.ndarray, Y: np.ndarray, beta_C_per_s: float,
                   a: float, b: float) -> Tuple[float, float]:
    m = (T >= a) & (T <= b)
    if not np.any(m) or not beta_C_per_s:
        return np.nan, np.nan
    x = T[m]; y = Y[m]
    pk = int(np.nanargmin(y))  # exotherm down
    base = local_baseline(x, y, pk_idx=pk, pad=10.0, side=6.0)
    area = -np.trapz((y - base) / beta_C_per_s, x)  # make positive
    Tc = float(x[pk])
    return abs(float(area)), Tc

def tg_from_inflection(T: np.ndarray, Y: np.ndarray, a: float, b: float) -> float:
    m = (T >= a) & (T <= b)
    if not np.any(m): return np.nan
    from scipy.ndimage import gaussian_filter1d
    xs = T[m]; ys = gaussian_filter1d(Y[m], sigma=7)
    dy = np.gradient(ys, xs)
    idx = int(np.nanargmin(dy))  # falling step
    return float(xs[idx])

# ---------------- Results ----------------
def compute_typeIII(df: pd.DataFrame, material: str, unit_sel: str,
                    dH0: float = 130.0, polymer_fraction: float = 1.0) -> Dict[str, Optional[float]]:
    seg1, segC, seg2 = split_cycles(df)
    R = ranges_for(material)

    beta_s = df.attrs.get("beta_C_per_s", np.nan)

    # choose unit
    mass_g = df.attrs.get("mass_g", np.nan)
    if unit_sel == "Auto":
        unit_mode = choose_unit_auto(seg2, mass_g, beta_s, R["melt"] if R["melt"][0] else (250, 380))
    else:
        unit_mode = "mw" if unit_sel == "mW" else "wpg"

    # convert all to W/g for calc; also build mW for display later
    def wpg(seg):
        raw = seg["Heat Flow (raw)"].to_numpy()
        return raw_to_Wpg(raw, mass_g, unit_mode)

    # attach arrays
    T1 = seg1["Temperature (C)"].to_numpy(); Y1 = wpg(seg1)
    T2 = seg2["Temperature (C)"].to_numpy(); Y2 = wpg(seg2)
    TC = segC["Temperature (C)"].to_numpy(); YC = wpg(segC)

    out = {"Tg (C)": None, "Tm (C)": None, "Tc (C)": None,
           "dHm (J/g)": None, "dHcc (J/g)": None, "dHc (J/g)": None,
           "Xc (%)": None, "_unit_mode": unit_mode}

    # Tg from 2nd heating
    tg = tg_from_inflection(T2, Y2, R["tg"][0], R["tg"][1])
    if np.isfinite(tg): out["Tg (C)"] = round(tg, 2)

    # Melt on H2 (local baseline)
    if R["melt"][0] is not None and not np.isnan(beta_s):
        a, b = R["melt"]
        dHm = melt_area_local(T2, Y2, beta_s, a, b)
        if np.isfinite(dHm): out["dHm (J/g)"] = round(dHm, 2)
        # Tm ~ peak within window
        m = (T2 >= a) & (T2 <= b)
        if np.any(m):
            pk = int(np.nanargmax(Y2[m])); out["Tm (C)"] = round(float(T2[m][pk]), 2)

    # Cooling crystal
    if R["cool"][0] is not None and not np.isnan(beta_s):
        a, b = R["cool"]
        dHc, Tc = exo_area_local(TC, YC, beta_s, a, b)
        if np.isfinite(dHc): out["dHc (J/g)"] = round(dHc, 2)
        if np.isfinite(Tc): out["Tc (C)"] = round(Tc, 2)

    # Cold crystal on H1
    if R["hcc"][0] is not None and not np.isnan(beta_s):
        a, b = R["hcc"]
        dHcc, _ = exo_area_local(T1, Y1, beta_s, a, b)
        if np.isfinite(dHcc): out["dHcc (J/g)"] = round(dHcc, 2)

    # Crystallinity
    if out["dHm (J/g)"] is not None:
        dHm = out["dHm (J/g)"]; dHcc = out["dHcc (J/g)"] or 0.0
        Xc = (dHm - dHcc) / (dH0 * polymer_fraction) * 100.0
        out["Xc (%)"] = round(Xc, 2)

    return out

# ---------------- UI State ----------------
st.session_state.setdefault("lib", {})
st.session_state.setdefault("staged", [])

st.title("DSC Library")

# Upload block
st.subheader("Upload")
u_name = st.text_input("User Name / Custom Tag", value="")
files = st.file_uploader("Upload .txt files", type=["txt"], accept_multiple_files=True)

colA, colB = st.columns(2)
if colA.button("Stage files", disabled=not files):
    staged = []
    for f in files or []:
        b = f.read()
        hid = hashlib.md5(b + f.name.encode()).hexdigest()
        staged.append((hid, b, f.name))
    st.session_state["staged"] = staged
    st.success(f"{len(staged)} file(s) staged. Name below, then add to library.")

if colB.button("Clear staged"):
    st.session_state["staged"] = []

# Stage list
for hid, b, fname in list(st.session_state["staged"]):
    label = st.text_input("Label", value=(u_name or fname), key=f"lbl_{hid}")
    if st.button("Add to library", key=f"add_{hid}"):
        if hid in st.session_state["lib"]:
            st.info("Already exists, skipped.")
        else:
            st.session_state["lib"][hid] = {"bytes": b, "label": label, "filename": fname, "added": datetime.now().isoformat()}
        # remove from staged
        st.session_state["staged"] = [x for x in st.session_state["staged"] if x[0] != hid]
        safe_rerun()

st.subheader("Uploaded DSC Files")
for hid, rec in list(st.session_state["lib"].items()):
    c1, c2, c3 = st.columns([4, 3, 1])
    c1.write(f"{rec['filename']}")
    c2.write(rec["label"])
    if c3.button("Delete", key=f"del_{hid}"):
        del st.session_state["lib"][hid]
        safe_rerun()

# Analyzer
st.subheader("Select a file to analyze")
keys = list(st.session_state["lib"].keys())
sel = st.selectbox("Choose a file", options=keys, format_func=lambda k: st.session_state["lib"][k]["label"] if keys else "")

material = st.selectbox("Material", ["PEEK", "PEKK", "ULTEM", "OTHER"], index=1)
unit_sel = st.selectbox("Heat Flow Unit", ["Auto", "mW", "W/g"], index=0)
with st.expander("Advanced (dH0 and polymer fraction)"):
    dH0 = st.number_input("dH0 (J/g)", value=130.0, step=1.0)
    polymer_fraction = st.number_input("Polymer mass fraction", min_value=0.0, max_value=1.0, value=1.0, step=0.05)

if sel:
    rec = st.session_state["lib"][sel]
    df, meta = parse_ta_txt(rec["bytes"])

    # attach attrs needed in compute
    df.attrs["beta_C_per_s"] = meta.get("beta_C_per_s", np.nan)
    df.attrs["mass_g"] = meta.get("mass_g", np.nan)

    # top metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Sample Mass (mg)", f"{meta.get('mass_mg', float('nan')):.3f}")
    c2.metric("Heating Rate (C/min)", f"{meta.get('beta_C_per_min', float('nan')):.2f}")
    c3.metric("Raw unit hint", "W/g" if meta.get("raw_is_wpg_hint") else "mW")

    # Calculate results
    results = compute_typeIII(df, material, unit_sel, dH0, polymer_fraction)

    # Build display mW (for plot/table)
    mode_used = results["_unit_mode"]
    mass_g = df.attrs["mass_g"]
    raw = df["Heat Flow (raw)"].to_numpy()
    if mode_used == "wpg":
        # convert W/g to mW for display
        hf_mw = raw * mass_g * 1000.0
    else:
        hf_mw = raw

    df_disp = pd.DataFrame({
        "Time (min)": df["Time (min)"],
        "Temperature (C)": df["Temperature (C)"],
        "Heat Flow (mW)": hf_mw
    })
    st.markdown("### Raw Data")
    st.dataframe(df_disp, use_container_width=True, height=300)
    st.download_button("Download raw data (CSV)", df_disp.to_csv(index=False).encode("utf-8"),
                       file_name=f"{rec['label']}_raw.csv", mime="text/csv")

    st.markdown("### DSC Curve with Analysis")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_disp["Temperature (C)"], y=df_disp["Heat Flow (mW)"],
                             mode="lines", name="DSC", line=dict(width=3, color="#2563EB"),
                             hovertemplate="T=%{x:.2f} C<br>HF=%{y:.2f} mW<extra></extra>"))
    fig.update_layout(xaxis_title="Temperature (C)", yaxis_title="Heat Flow (mW)",
                      plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                      xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)"),
                      yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)"),
                      margin=dict(l=40, r=20, t=10, b=40))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "toImageButtonOptions": {"format": "png"}})

    st.markdown("### Calculated Results (Type III)")
    show = {k: v for k, v in results.items() if not k.startswith("_")}
    table = pd.DataFrame(show, index=["Result"])
    st.dataframe(table, use_container_width=True)
    st.info(";  ".join([f"{k} = {v}" for k, v in show.items()]))

    st.caption(
        f"beta = {meta.get('beta_C_per_min', float('nan')):.2f} C/min "
        f"({meta.get('beta_C_per_s', float('nan')):.4f} C/s). "
        f"Heat Flow mode = {results['_unit_mode']}. "
        "Computation: local-baseline corrected integrals over T, divided by beta, to get J/g. "
        "Type III rule: H2 -> Tg, Tm, dHm; Cooling -> Tc, dHc; H1 -> dHcc."
    )
else:
    st.info("Add a file to library, then select it here.")
