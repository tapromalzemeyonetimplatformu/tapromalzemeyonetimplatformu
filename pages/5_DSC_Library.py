# 5_DSC_Library.py — DSC Library (mW→W/g normalization + β correction; white plot)
# - Upload→Stage (dedup)→Name→Add to Library
# - Clean select list
# - Heat Flow displayed in mW (table & plot)
# - INTERNAL: mW → W → W/g (divide by mass), then integrate over T and divide by β (°C/s) → J/g
# - Type III strict: H2 for Tm/ΔHm, C for Tc/ΔHc, H1 for ΔHcc (no fallback)

import io, re, math, uuid, hashlib
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="DSC Library", page_icon="🔥", layout="wide")

# ---------------- Auth Guard -----------------
def require_auth():
    auth = (
        st.session_state.get("authenticated")
        or (isinstance(st.session_state.get("auth"), dict) and st.session_state["auth"].get("is_authenticated"))
        or bool(st.session_state.get("username"))
        or bool(st.session_state.get("auth_user"))
    )
    if not auth:
        st.error("Please log in to access DSC Library.")
        st.stop()
    user = (
        st.session_state.get("username")
        or st.session_state.get("auth_user")
        or (st.session_state.get("auth") or {}).get("user", {}).get("username")
        or (st.session_state.get("auth") or {}).get("username")
        or "unknown"
    )
    return str(user)

current_user = require_auth()

# ---------------- Constants ------------------
POLYMER_DH0_DEFAULTS = {"PEEK": 130.0, "PEKK": 130.0, "PPS": 112.0}
HEADER_KEYS = {
    "sample": ["Sample", "Sample Name"],
    "size_mg": ["Size", "Sample mass", "Mass", "Weight"],
    "orgmethod": ["OrgMethod", "Method", "Program"],
    "operator": ["Operator"],
    "file": ["File", "OrgFile"],
}

# ---------------- Helpers --------------------
def parse_header_and_data(text: str):
    lines = text.splitlines()
    # data start = first numeric line
    num_re = re.compile(r'^\s*[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?')
    start = None
    for i, l in enumerate(lines):
        if num_re.match(l.strip()):
            start = i; break
    header = lines[:start] if start is not None else []
    data_str = "\n".join(lines[start:]) if start is not None else ""

    H = {}
    for k, keys in HEADER_KEYS.items():
        for key in keys:
            for ln in header:
                if ln.startswith(key + "\t") or ln.startswith(key + " "):
                    parts = re.split(r"\t|\s{2,}", ln.strip())
                    if len(parts) >= 2:
                        H[k] = parts[1]; break
            if k in H: break

    # sample mass (mg)
    sample_mass_mg = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["size_mg"]):
            m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*mg', ln, flags=re.I)
            if m: sample_mass_mg = float(m.group(1)); break

    # heating rate from header: "Ramp X.XX C/min"
    heating_rate_header = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["orgmethod"]):
            m = re.search(r'Ramp\s+([0-9]+(?:\.[0-9]+)?)\s*C\s*/\s*min', ln, flags=re.I)
            if m: heating_rate_header = float(m.group(1)); break

    # data parse (≥3 cols: Time, Temp, HeatFlow)
    if data_str.strip():
        df = pd.read_csv(io.StringIO(data_str), delim_whitespace=True, header=None, engine="python")
        if df.shape[1] >= 3:
            cols = ["Time", "Temp", "HeatFlow"] + [f"c{i}" for i in range(3, df.shape[1])]
            df.columns = cols[: df.shape[1]]
            if "HeatFlow" not in df.columns:
                df["HeatFlow"] = df.iloc[:, -1]
        else:
            df = pd.DataFrame(columns=["Time", "Temp", "HeatFlow"])
    else:
        df = pd.DataFrame(columns=["Time", "Temp", "HeatFlow"])

    meta = {
        "sample_name": H.get("sample", ""),
        "sample_mass_mg": sample_mass_mg,            # mg
        "operator": H.get("operator", ""),
        "file": H.get("file", ""),
        "heating_rate_header": heating_rate_header,  # °C/min
    }
    return meta, df[["Time", "Temp", "HeatFlow"]].copy()

def run_split(df: pd.DataFrame):
    """Split into Heating1 → Cooling → Heating2 (robust)."""
    if df.empty or len(df) < 50:
        return df.copy(), pd.DataFrame(), pd.DataFrame()
    T = df["Temp"].to_numpy()
    dT = np.diff(T, prepend=T[0])

    from scipy.ndimage import uniform_filter1d
    dTs = uniform_filter1d(dT, size=41, mode="nearest")
    sign = np.sign(dTs)

    blocks, start = [], 0
    for i in range(1, len(sign)):
        if sign[i] != sign[i - 1]:
            if i - start > 30:
                blocks.append((start, i))
            start = i
    if len(sign) - start > 30:
        blocks.append((start, len(sign)))

    heats = [(a, b) for (a, b) in blocks if np.mean(dTs[a:b]) >= 0]
    cools = [(a, b) for (a, b) in blocks if np.mean(dTs[a:b]) < 0]

    H1 = heats[0] if heats else None
    C  = next(((a, b) for (a, b) in cools if H1 and a > H1[1]), None)
    H2 = next(((a, b) for (a, b) in heats if C and a > C[1]), None)

    def slice_blk(blk):
        return df.iloc[blk[0]:blk[1]].reset_index(drop=True) if blk else pd.DataFrame(columns=df.columns)

    return slice_blk(H1), slice_blk(C), slice_blk(H2)

def calc_heating_rate(df):
    """Compute °C/min by linear regression."""
    if df.empty or len(df) < 10:
        return None
    t = df["Time"].to_numpy()      # (usually minutes in TA export)
    T = df["Temp"].to_numpy()
    q10, q90 = np.quantile(np.arange(len(T)), [0.1, 0.9]).astype(int)
    if q90 <= q10:
        return None
    tt = t[q10:q90]; TT = T[q10:q90]
    A = np.vstack([tt, np.ones_like(tt)]).T
    m, _ = np.linalg.lstsq(A, TT, rcond=None)[0]  # °C per minute (assumed)
    return float(m)

# ---------- Core thermogram helpers ----------
def line_baseline(x, y):
    y0, y1 = y[0], y[-1]; x0, x1 = x[0], x[-1]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0 + 1e-12)

def area_J_per_g_over_T(T, Y_W_per_g, a, b, beta_C_per_s):
    """Linear-baseline corrected area over T, then divide by β (°C/s) to get J/g."""
    m = (T >= a) & (T <= b)
    if not np.any(m) or beta_C_per_s is None or beta_C_per_s <= 0:
        return np.nan
    x = T[m]; y = Y_W_per_g[m]
    base = line_baseline(x, y)
    area_Wpg_degC = float(np.trapz(y - base, x))     # [W/g * °C]
    return area_Wpg_degC / beta_C_per_s              # [J/g]

def peak_T(T, Y, a, b, mode="min"):
    m = (T >= a) & (T <= b)
    if not np.any(m): return np.nan
    idx = np.nanargmin(Y[m]) if mode == "min" else np.nanargmax(Y[m])
    return float(T[m][idx])

def endo_is_down(T, Y, a, b):
    m = (T >= a) & (T <= b)
    if not np.any(m): return True
    seg = Y[m]
    return abs(np.nanmin(seg)) >= abs(np.nanmax(seg))

def tg_inflection(T, Y, a, b):
    m = (T >= a) & (T <= b)
    if not np.any(m): return np.nan
    from scipy.ndimage import gaussian_filter1d
    x = T[m]; y = gaussian_filter1d(Y[m], sigma=7)
    dy = np.gradient(y, x)
    idx = np.nanargmax(np.abs(dy))
    return float(x[idx])

def default_ranges(material: str):
    m = (material or "").upper()
    if m.startswith("PEEK"):
        return {"tg": (120, 170), "hm": (300, 385), "hc": (180, 280), "hcc": (150, 260)}
    if m.startswith("PEKK"):
        return {"tg": (130, 170), "hm": (290, 380), "hc": (160, 270), "hcc": (150, 260)}
    if m.startswith("PPS"):
        return {"tg": (70, 110),  "hm": (240, 300), "hc": (150, 220), "hcc": (None, None)}
    return {"tg": (50, 200), "hm": (150, 400), "hc": (80, 300), "hcc": (None, None)}

def compute_typeIII_strict(meta, df_all, H1, C, H2, material, dh0, polymer_frac, hr_calc):
    """Strict Type III without fallback; convert mW → W/g; divide by β (°C/s)."""
    mass_mg = meta.get("sample_mass_mg")
    mass_g = mass_mg / 1000.0 if mass_mg else None
    beta_C_per_min = meta.get("heating_rate_header") or hr_calc   # °C/min
    beta_C_per_s = (beta_C_per_min / 60.0) if beta_C_per_min else None

    R = default_ranges(material)
    # Prepare W/g arrays for each segment
    def arr_Wpg(D):
        if D.empty or not mass_g or mass_g <= 0:
            return None, None
        T = D["Temp"].to_numpy()
        HF_mW = D["HeatFlow"].to_numpy()          # assume raw is mW (total power)
        Y_Wpg = (HF_mW / 1000.0) / mass_g         # W/g
        return T, Y_Wpg

    results = {"Tg (°C)": None, "Tm (°C)": None, "Tc (°C)": None,
               "ΔHm (J/g)": None, "ΔHcc (J/g)": None, "ΔHc (J/g)": None, "Crystallinity Xc (%)": None}

    # Tg from H2
    if not H2.empty:
        T2, Y2_Wpg = arr_Wpg(H2)
        if T2 is not None:
            results["Tg (°C)"] = round(tg_inflection(T2, Y2_Wpg, *R["tg"]), 2)

    # Tm & ΔHm from H2
    if not H2.empty and beta_C_per_s:
        T2, Y2_Wpg = arr_Wpg(H2)
        if T2 is not None:
            hm_down = endo_is_down(T2, Y2_Wpg, *R["hm"])
            results["Tm (°C)"] = round(peak_T(T2, Y2_Wpg, *R["hm"], mode=("min" if hm_down else "max")), 2)
            dHm = area_J_per_g_over_T(T2, Y2_Wpg, *R["hm"], beta_C_per_s)
            if not (dHm is None or math.isnan(dHm)): results["ΔHm (J/g)"] = round(abs(dHm), 2)

    # Tc & ΔHc from Cooling
    if not C.empty and beta_C_per_s:
        Tc_T, Tc_Y = arr_Wpg(C)
        if Tc_T is not None:
            results["Tc (°C)"] = round(peak_T(Tc_T, Tc_Y, *R["hc"], mode="min"), 2)
            dHc = area_J_per_g_over_T(Tc_T, Tc_Y, *R["hc"], beta_C_per_s)
            if not (dHc is None or math.isnan(dHc)): results["ΔHc (J/g)"] = round(abs(dHc), 2)

    # ΔHcc from H1
    if not H1.empty and all(v is not None for v in R["hcc"]) and beta_C_per_s:
        T1, Y1_Wpg = arr_Wpg(H1)
        if T1 is not None:
            dHcc = area_J_per_g_over_T(T1, Y1_Wpg, *R["hcc"], beta_C_per_s)
            if not (dHcc is None or math.isnan(dHcc)): results["ΔHcc (J/g)"] = round(abs(dHcc), 2)

    # Crystallinity: Xc = ((ΔHm - ΔHcc) / (ΔH° * polymer_fraction)) * 100
    dHm = results["ΔHm (J/g)"]; dHcc = results["ΔHcc (J/g)"]
    if dHm is not None and polymer_frac and dh0 and dh0 > 0:
        corr = dHm - (dHcc or 0.0)
        Xc = (corr / (dh0 * polymer_frac)) * 100.0
        results["Crystallinity Xc (%)"] = round(Xc, 2)

    return results, beta_C_per_s

# ---------------- State ----------------------
st.title("DSC Library")
if "dsc_files" not in st.session_state: st.session_state["dsc_files"] = {}
if "pending_uploads" not in st.session_state: st.session_state["pending_uploads"] = []
if "seen_upload_ids" not in st.session_state: st.session_state["seen_upload_ids"] = set()

# ---------------- Upload (Form + Submit + Dedup) ---------------------
st.header("Upload")
with st.form("uploader_form"):
    new_files = st.file_uploader("Upload DSC .txt files", type=["txt"], accept_multiple_files=True, key="dsc_uploader")
    staged = st.form_submit_button("Stage files")
if staged and new_files:
    added = 0
    for f in new_files:
        content = f.getvalue()
        fid = hashlib.md5(content + f.name.encode()).hexdigest()
        if fid in st.session_state["seen_upload_ids"]:
            continue
        st.session_state["seen_upload_ids"].add(fid)
        st.session_state["pending_uploads"].append({
            "tmp_key": uuid.uuid4().hex, "file_id": fid, "orig_name": f.name,
            "bytes": content, "user_name": f.name
        }); added += 1
    if added: st.success(f"{added} file(s) staged. Name them below, then add to library.")
    st.session_state.pop("dsc_uploader", None); st.experimental_rerun()

# ----------- Pre-naming & Add to Library -----
if st.session_state["pending_uploads"]:
    st.subheader("Name your upload(s)")
    if st.button("Add ALL to Library"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in st.session_state["pending_uploads"]:
            key = uuid.uuid4().hex
            st.session_state["dsc_files"][key] = {
                "orig_name": item["orig_name"], "user_name": item["user_name"],
                "uploader": current_user, "uploaded_at": now, "bytes": item["bytes"]
            }
            st.session_state["seen_upload_ids"].discard(item.get("file_id",""))
        st.session_state["pending_uploads"].clear(); st.experimental_rerun()

    remove_keys = []
    for item in st.session_state["pending_uploads"]:
        c1, c2, c3 = st.columns([4, 4, 1])
        c1.write(item["orig_name"])
        new_nm = c2.text_input("User Name", value=item["user_name"], key=f"pending_name_{item['tmp_key']}")
        item["user_name"] = new_nm
        if c3.button("Add to Library", key=f"add_{item['tmp_key']}"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            key = uuid.uuid4().hex
            st.session_state["dsc_files"][key] = {
                "orig_name": item["orig_name"], "user_name": item["user_name"],
                "uploader": current_user, "uploaded_at": now, "bytes": item["bytes"]
            }
            st.session_state["seen_upload_ids"].discard(item.get("file_id",""))
            remove_keys.append(item["tmp_key"])
    if remove_keys:
        st.session_state["pending_uploads"] = [x for x in st.session_state["pending_uploads"] if x["tmp_key"] not in remove_keys]
        st.experimental_rerun()

# ---------------- Uploaded List --------------
st.header("Uploaded DSC Files")
if not st.session_state["dsc_files"]:
    st.info("No files in library yet. Upload above, name them, then click Add to Library.")
else:
    for key, rec in list(st.session_state["dsc_files"].items()):
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 1])
        c1.write(rec["orig_name"]); c2.write(rec["user_name"]); c3.write(rec["uploader"]); c4.write(rec["uploaded_at"])
        if c5.button("Delete", key=f"del_{key}"):
            del st.session_state["dsc_files"][key]; st.experimental_rerun()

# ---------------- Selection ------------------
st.header("Select a file to analyze")
def file_label(key: str) -> str:
    rec = st.session_state["dsc_files"][key]; return f"{rec['user_name']} ({rec['orig_name']})"
options = list(st.session_state["dsc_files"].keys())
selected_key = st.selectbox("Choose a file", options=options, format_func=(file_label if options else None))
dsc_type = st.selectbox("Type", options=["Type III", "Type II", "Type I"], index=0)
material = st.selectbox("Material", options=["PEEK", "PEKK", "PPS", "OTHER"], index=0)
with st.expander("Advanced (ΔH° and polymer fraction)"):
    default_dh0 = POLYMER_DH0_DEFAULTS.get(material, 130.0)
    dh0 = st.number_input("ΔH° (J/g)", value=float(default_dh0), step=1.0, format="%.2f")
    polymer_frac = st.number_input("Polymer mass fraction (1 − filler wt. fraction)", min_value=0.0, max_value=1.0, value=1.0, step=0.05)

# ---------------- Analysis -------------------
if selected_key:
    raw = st.session_state["dsc_files"][selected_key]["bytes"].decode("utf-8", "ignore")
    meta, df = parse_header_and_data(raw)

    # split + HR
    H1, C, H2 = run_split(df)
    hr_calc_candidates = [r for seg in [H1, H2] if (r := calc_heating_rate(seg)) and r > 0]
    hr_calc = float(np.median(hr_calc_candidates)) if hr_calc_candidates else calc_heating_rate(df)

    # top metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Sample Mass (mg)", f"{meta.get('sample_mass_mg') if meta.get('sample_mass_mg') is not None else '—'}")
    hr_show = meta.get("heating_rate_header")
    m2.metric("Heating Rate (°C/min)", f"{(hr_show if hr_show is not None else (round(hr_calc, 2) if hr_calc else '—'))}")
    m3.metric("Operator", meta.get("operator") or "—")
    if meta.get("heating_rate_header") and hr_calc:
        if abs(hr_calc - meta["heating_rate_header"]) / max(meta["heating_rate_header"], 1e-6) > 0.10:
            st.warning(f"Header HR={meta['heating_rate_header']:.2f} °C/min, Calculated HR={hr_calc:.2f} °C/min (check program).")

    # Raw data (display in mW) + download
    st.subheader("Raw Data")
    df_disp = pd.DataFrame({
        "Time (min)": df["Time"],
        "Temperature (°C)": df["Temp"],
        "Heat Flow (mW)": df["HeatFlow"]  # assuming raw is mW
    })
    st.dataframe(df_disp, use_container_width=True, height=300)
    st.download_button("⬇️ Download raw data (CSV)", df_disp.to_csv(index=False).encode("utf-8"),
                       file_name=f"{(meta.get('sample_name') or 'sample')}_raw.csv", mime="text/csv")

    # Plot (white background), y in mW
    st.subheader("DSC Curve with Analysis")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Temp"], y=df["HeatFlow"],
        mode="lines", name="DSC",
        line=dict(width=3, color="#2563EB"),
        hovertemplate="T = %{x:.2f} °C<br>HF = %{y:.2f} mW<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Temperature (°C)", yaxis_title="Heat Flow (mW)",
        legend_title="",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)"),
        margin=dict(l=40, r=20, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "toImageButtonOptions": {"format": "png"}})

    # Results — strict Type III with proper units
    st.subheader("Calculated Results (Type III)")
    results, beta_C_per_s = compute_typeIII_strict(meta, df, H1, C, H2, material, dh0, polymer_frac, hr_calc)
    st.dataframe(pd.DataFrame(results, index=["Result"]), use_container_width=True)

    # short summary
    order = ["Tg (°C)", "Tm (°C)", "Tc (°C)", "ΔHm (J/g)", "ΔHcc (J/g)", "ΔHc (J/g)", "Crystallinity Xc (%)"]
    items = [f"{k.replace(' (°C)','').replace(' (J/g)','')} = {results[k]}" for k in order if results.get(k) is not None]
    st.info(";  ".join(items) if items else "No calculable result (missing segment or ranges).")
    st.caption(f"β = {(meta.get('heating_rate_header') or hr_calc or 0):.2f} °C/min ({(beta_C_per_s or 0):.4f} °C/s).  ΔH°={dh0:.1f} J/g; polymer fraction={polymer_frac:.2f}.  "
               "Tm/ΔHm from 2nd heating; Tc/ΔHc from cooling; ΔHcc from 1st heating. mW→W→W/g and division by β applied.")
else:
    st.info("Select a file to analyze.")
