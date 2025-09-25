# pages/5_DSC_Library.py  --  DSC Library (peak-narrowed, stable)

import io, re, math, hashlib
from datetime import datetime
from typing import Tuple, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="DSC Library", page_icon="🔥", layout="wide")

# ----------------- Small utils -----------------
def safe_rerun():
    try: st.rerun()
    except Exception: pass

def sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1(); h.update(b); return h.hexdigest()

def r2(x):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), 2)

# ----------------- Parse TA txt -----------------
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

        if data_start is None and re.match(r"^[\s.+-Ee0-9]+\s+[\s.+-Ee0-9]+\s+[\s.+-Ee0-9]+$", s):
            data_start = i

    if data_start is None:
        for i, ln in enumerate(lines):
            if re.match(r"^\s*\.?[0-9Ee+-]+\s+\.?[0-9Ee+-]+\s+\.?[0-9Ee+-]+\s*$", ln):
                data_start = i; break

    rows = []
    for ln in lines[data_start:]:
        s = re.sub(r"(^|\s)\.(\d)", r"\g<1>0.\2", ln.strip())
        parts = s.split()
        if len(parts) != 3: continue
        try:
            t = float(parts[0]); T = float(parts[1]); q = float(parts[2])
            rows.append((t, T, q))
        except: continue

    df = pd.DataFrame(rows, columns=["Time (min)", "Temperature (C)", "Heat Flow (raw)"])

    # heating rate (C/min and C/s)
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
    meta["beta_C_per_s"] = (beta / 60.0) if beta else np.nan

    mg = meta.get("size_mg", np.nan)
    meta["mass_mg"] = mg
    meta["mass_g"] = (mg / 1000.0) if (mg and not math.isnan(mg)) else np.nan

    hint = (meta.get("sig3") or "") + " " + (meta.get("hfmode") or "")
    meta["raw_is_wpg_hint"] = ("W/g" in hint)

    return df, meta

# ----------------- Segmentation -----------------
def split_cycles(df: pd.DataFrame):
    T = df["Temperature (C)"].to_numpy()
    t = df["Time (min)"].to_numpy()
    if len(T) < 50:
        n = len(T); i1, i2 = n // 3, 2 * n // 3
        return df.iloc[:i1].reset_index(drop=True), df.iloc[i1:i2].reset_index(drop=True), df.iloc[i2:].reset_index(drop=True)
    dTdt = np.gradient(T, t)
    from scipy.signal import medfilt
    s = medfilt(np.sign(dTdt), kernel_size=51)
    cuts = np.where(np.diff(s) != 0)[0] + 1
    if len(cuts) >= 2:
        i1, i2 = cuts[0], cuts[1]
    else:
        n = len(T); i1, i2 = n // 3, 2 * n // 3
    return df.iloc[:i1].reset_index(drop=True), df.iloc[i1:i2].reset_index(drop=True), df.iloc[i2:].reset_index(drop=True)

# ----------------- Units -----------------
def raw_to_Wpg(raw: np.ndarray, mass_g: float, mode: str) -> np.ndarray:
    if mode == "wpg":
        return raw.astype(float)
    return (raw.astype(float) / 1000.0) / mass_g  # mW -> W -> /g

def choose_unit_auto(H2: pd.DataFrame, mass_g: float, beta_s: float, melt_window: Tuple[float, float]) -> str:
    if not mass_g or np.isnan(mass_g) or H2.empty or not beta_s: return "mw"
    T = H2["Temperature (C)"].to_numpy()
    q = H2["Heat Flow (raw)"].to_numpy()
    a, b = melt_window
    d_mw = abs(melt_area_local(T, raw_to_Wpg(q, mass_g, "mw"), beta_s, a, b))
    d_wg = abs(melt_area_local(T, raw_to_Wpg(q, mass_g, "wpg"), beta_s, a, b))
    def score(d):
        if 5 <= d <= 150: return abs(80 - d) * 0.01
        if 1 <= d <= 200: return abs(80 - d) * 0.05
        return abs(d - 80) * 0.5 + 100
    return "mw" if score(d_mw) <= score(d_wg) else "wpg"

# ----------------- Windows -----------------
REF = {
    "PEEK":  {"tg": (120,170), "melt": (300,385), "cool": (180,280), "hcc": (150,260)},
    "PEKK":  {"tg": (150,170), "melt": (295,360), "cool": (200,270), "hcc": (180,260)},
    "ULTEM": {"tg": (180,230), "melt": (None,None), "cool": (None,None), "hcc": (None,None)},
    "OTHER": {"tg": (50,200),  "melt": (150,400), "cool": (80,300),  "hcc": (120,300)},
}
def ranges_for(material: str):
    return REF.get((material or "").upper(), REF["OTHER"])

# ----------------- Baseline & areas -----------------
def local_baseline(x: np.ndarray, y: np.ndarray, pk_idx: int, pad: float = 6.0, side: float = 4.0) -> np.ndarray:
    xl = x[(x >= x[pk_idx] - pad - side) & (x <= x[pk_idx] - pad)]
    xr = x[(x >= x[pk_idx] + pad) & (x <= x[pk_idx] + pad + side)]
    yl = y[(x >= x[pk_idx] - pad - side) & (x <= x[pk_idx] - pad)]
    yr = y[(x >= x[pk_idx] + pad) & (x <= x[pk_idx] + pad + side)]
    if len(xl) < 3 or len(xr) < 3:
        x0, x1 = x[0], x[-1]; y0, y1 = y[0], y[-1]
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0 + 1e-12)
    xl_m, yl_m = np.mean(xl), np.mean(yl); xr_m, yr_m = np.mean(xr), np.mean(yr)
    return yl_m + (yr_m - yl_m) * (x - xl_m) / (xr_m - xl_m + 1e-12)

def auto_peak_idx(y: np.ndarray) -> int:
    # decide endo/exo automatically: larger absolute extremum wins
    i_max = int(np.nanargmax(y)); i_min = int(np.nanargmin(y))
    return i_max if abs(y[i_max]) >= abs(y[i_min]) else i_min

def melt_area_local(T: np.ndarray, Y: np.ndarray, beta_s: float, a: float, b: float) -> float:
    m = (T >= a) & (T <= b)
    if not np.any(m) or not beta_s: return np.nan
    x = T[m]; y = Y[m]
    pk = auto_peak_idx(y)  # endo/exo bağımsız, alan mutlak alınacak
    base = local_baseline(x, y, pk_idx=pk, pad=6.0, side=4.0)
    area = np.trapz((y - base) / beta_s, x)
    return abs(float(area))

def exo_area_local(T: np.ndarray, Y: np.ndarray, beta_s: float, a: float, b: float) -> Tuple[float, float]:
    m = (T >= a) & (T <= b)
    if not np.any(m) or not beta_s: return np.nan, np.nan
    x = T[m]; y = Y[m]
    pk = auto_peak_idx(-y)  # exo için aşağı yön
    base = local_baseline(x, y, pk_idx=pk, pad=6.0, side=4.0)
    area = -np.trapz((y - base) / beta_s, x)
    Tc = float(x[pk])
    return abs(float(area)), Tc

def narrow_window_around_peak(T: np.ndarray, Y: np.ndarray, a: float, b: float, halfspan: float) -> Tuple[float,float,float]:
    """return (a', b', Tpk) where Tpk is peak temperature; window narrowed to ±halfspan"""
    m = (T >= a) & (T <= b)
    if not np.any(m): return a, b, float("nan")
    x = T[m]; y = Y[m]
    pk = auto_peak_idx(y)
    Tpk = float(x[pk])
    return max(a, Tpk - halfspan), min(b, Tpk + halfspan), Tpk

def tg_from_inflection(T: np.ndarray, Y: np.ndarray, a: float, b: float) -> float:
    m = (T >= a) & (T <= b)
    if not np.any(m): return np.nan
    from scipy.ndimage import gaussian_filter1d
    xs = T[m]; ys = gaussian_filter1d(Y[m], sigma=7)
    dy = np.gradient(ys, xs)
    idx = int(np.nanargmin(abs(dy)))  # en büyük değişim civarı
    return float(xs[idx])

# ----------------- Computation (Type III) -----------------
def compute_typeIII(df: pd.DataFrame, material: str, unit_sel: str,
                    dH0: float = 130.0, polymer_fraction: float = 1.0) -> Dict[str, Optional[float]]:
    H1, C, H2 = split_cycles(df)
    R = ranges_for(material)
    beta_s = df.attrs.get("beta_C_per_s", np.nan)
    mass_g = df.attrs.get("mass_g", np.nan)

    # unit choose
    if unit_sel == "Auto":
        unit_mode = choose_unit_auto(H2, mass_g, beta_s, R["melt"] if R["melt"][0] else (250, 380))
    else:
        unit_mode = "mw" if unit_sel == "mW" else "wpg"

    def to_wpg(seg):
        return raw_to_Wpg(seg["Heat Flow (raw)"].to_numpy(), mass_g, unit_mode)

    T1, Y1 = H1["Temperature (C)"].to_numpy(), to_wpg(H1)
    TC, YC = C["Temperature (C)"].to_numpy(),  to_wpg(C)
    T2, Y2 = H2["Temperature (C)"].to_numpy(), to_wpg(H2)

    out = {"Tg (C)": None, "Tm (C)": None, "Tc (C)": None,
           "dHm (J/g)": None, "dHcc (J/g)": None, "dHc (J/g)": None,
           "Xc (%)": None, "_unit_mode": unit_mode}

    # Tg (H2)
    tg = tg_from_inflection(T2, Y2, R["tg"][0], R["tg"][1])
    if np.isfinite(tg): out["Tg (C)"] = r2(tg)

    # Melt (H2) with ±12 C narrowing
    if R["melt"][0] is not None and not np.isnan(beta_s):
        a, b = R["melt"]
        a2, b2, Tm = narrow_window_around_peak(T2, Y2, a, b, halfspan=12.0)
        dHm = melt_area_local(T2, Y2, beta_s, a2, b2)
        if np.isfinite(dHm): out["dHm (J/g)"] = r2(dHm)
        if np.isfinite(Tm):  out["Tm (C)"] = r2(Tm)

    # Cooling (exo) with ±12 C narrowing around peak
    if R["cool"][0] is not None and not np.isnan(beta_s):
        a, b = R["cool"]
        a2, b2, Tc = narrow_window_around_peak(TC, YC, a, b, halfspan=12.0)
        dHc, Tc_pk = exo_area_local(TC, YC, beta_s, a2, b2)
        if np.isfinite(dHc): out["dHc (J/g)"] = r2(dHc)
        if np.isfinite(Tc_pk): out["Tc (C)"] = r2(Tc_pk)

    # Hcc (H1) with ±10 C narrowing
    if R["hcc"][0] is not None and not np.isnan(beta_s):
        a, b = R["hcc"]
        a2, b2, _ = narrow_window_around_peak(T1, Y1, a, b, halfspan=10.0)
        dHcc, _ = exo_area_local(T1, Y1, beta_s, a2, b2)
        if np.isfinite(dHcc): out["dHcc (J/g)"] = r2(dHcc)

    # Crystallinity
    if out["dHm (J/g)"] is not None:
        corr = out["dHm (J/g)"] - (out["dHcc (J/g)"] or 0.0)
        out["Xc (%)"] = r2((corr / (dH0 * polymer_fraction)) * 100.0)

    return out

# ----------------- UI state -----------------
st.session_state.setdefault("lib", {})
st.session_state.setdefault("staged", [])

st.title("DSC Library")

# ---------- Upload & Stage ----------
st.subheader("Upload")
user_label = st.text_input("User Name / Custom Tag", value="")
up_files = st.file_uploader("Upload .txt files", type=["txt"], accept_multiple_files=True)

cA, cB = st.columns(2)
if cA.button("Stage files", disabled=not up_files):
    staged = []
    for f in up_files or []:
        b = f.read()
        hid = hashlib.md5(b + f.name.encode()).hexdigest()
        staged.append((hid, b, f.name))
    st.session_state["staged"] = staged
    st.success(f"{len(staged)} file(s) staged. Name below, then add to library.")

if cB.button("Clear staged"):
    st.session_state["staged"] = []

for hid, b, fname in list(st.session_state["staged"]):
    label = st.text_input("Label", value=(user_label or fname), key=f"lbl_{hid}")
    if st.button("Add to library", key=f"add_{hid}"):
        if hid in st.session_state["lib"]:
            st.info("Already exists, skipped.")
        else:
            st.session_state["lib"][hid] = {
                "bytes": b, "label": label, "filename": fname, "added": datetime.now().isoformat()
            }
        st.session_state["staged"] = [x for x in st.session_state["staged"] if x[0] != hid]
        safe_rerun()

# ---------- Library list ----------
st.subheader("Uploaded DSC Files")
for hid, rec in list(st.session_state["lib"].items()):
    c1, c2, c3 = st.columns([4, 3, 1])
    c1.write(rec["filename"])
    c2.write(rec["label"])
    if c3.button("Delete", key=f"del_{hid}"):
        del st.session_state["lib"][hid]
        safe_rerun()

# ---------- Analyzer ----------
st.subheader("Select a file to analyze")
keys = list(st.session_state["lib"].keys())
sel = st.selectbox("Choose a file", options=keys, format_func=lambda k: st.session_state["lib"][k]["label"] if keys else "")

material = st.selectbox("Material", ["PEEK","PEKK","ULTEM","OTHER"], index=1)
unit_sel = st.selectbox("Heat Flow Unit", ["Auto","mW","W/g"], index=0)
with st.expander("Advanced (dH0 and polymer fraction)"):
    dH0 = st.number_input("dH0 (J/g)", value=130.0, step=1.0)
    polymer_fraction = st.number_input("Polymer mass fraction", min_value=0.0, max_value=1.0, value=1.0, step=0.05)

if sel:
    rec = st.session_state["lib"][sel]
    df, meta = parse_ta_txt(rec["bytes"])
    df.attrs["beta_C_per_s"] = meta.get("beta_C_per_s", np.nan)
    df.attrs["mass_g"] = meta.get("mass_g", np.nan)

    # top metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Sample Mass (mg)", f"{meta.get('mass_mg', float('nan')):.3f}")
    m2.metric("Heating Rate (C/min)", f"{meta.get('beta_C_per_min', float('nan')):.2f}")
    m3.metric("Raw unit hint", "W/g" if meta.get("raw_is_wpg_hint") else "mW")

    # compute
    res = compute_typeIII(df, material, unit_sel, dH0, polymer_fraction)

    # display mW
    mode_used = res["_unit_mode"]
    mass_g = df.attrs["mass_g"]
    raw = df["Heat Flow (raw)"].to_numpy()
    if mode_used == "wpg":
        hf_mw = raw * mass_g * 1000.0
    else:
        hf_mw = raw
    df_disp = pd.DataFrame({"Time (min)": df["Time (min)"], "Temperature (C)": df["Temperature (C)"], "Heat Flow (mW)": hf_mw})

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
    show = {k: v for k, v in res.items() if not k.startswith("_")}
    table = pd.DataFrame(show, index=["Result"])
    st.dataframe(table, use_container_width=True)

    order = ["Tg (C)","Tm (C)","Tc (C)","dHm (J/g)","dHcc (J/g)","dHc (J/g)","Xc (%)"]
    st.info(";  ".join([f"{k} = {res[k]}" for k in order if res.get(k) is not None]))

    st.caption(
        f"beta = {meta.get('beta_C_per_min', float('nan')):.2f} C/min ({meta.get('beta_C_per_s', float('nan')):.4f} C/s). "
        f"Heat Flow mode = {res['_unit_mode']}. "
        "Computation: local-baseline corrected integrals; H2: Tg/Tm/dHm (melt window ±12 C), "
        "Cooling: Tc/dHc (±12 C), H1: dHcc (±10 C). Xc = (dHm - dHcc)/(dH0*polymer_fraction)*100."
    )
else:
    st.info("Add a file to library, then select it here.")
