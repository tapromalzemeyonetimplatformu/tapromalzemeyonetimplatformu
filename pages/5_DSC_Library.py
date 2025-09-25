# 5_DSC_Library.py — DSC Library
# Features:
# - Auth guard (requires a logged-in session)
# - Upload → Stage (form) → Pre-name → Add to Library (dedup with MD5)
# - Library table (Original, User Name, Uploader, Time, Delete)
# - Clean select list (User Name (Original))
# - Correct heating-rate read (header) + robust fallback (regression on H1/H2)
# - Raw Data table with units + CSV download
# - Single clean DSC curve (download from Plotly modebar)
# - Type III one-block results: Tg, Tm, Tc, ΔHm, ΔHcc, ΔHc, Xc
# - Endotherm direction auto-detect; linear-baseline integration
# - ΔH° and polymer mass fraction adjustable

import io, re, math, uuid, hashlib
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ---------------- Page Config ----------------
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

    # first numeric line = data start
    num_re = re.compile(r'^\s*[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?')
    start = None
    for i, l in enumerate(lines):
        if num_re.match(l.strip()):
            start = i
            break

    header = lines[:start] if start is not None else []
    data_str = "\n".join(lines[start:]) if start is not None else ""

    # header capture
    H = {}
    for k, keys in HEADER_KEYS.items():
        for key in keys:
            for ln in header:
                if ln.startswith(key + "\t") or ln.startswith(key + " "):
                    parts = re.split(r"\t|\s{2,}", ln.strip())
                    if len(parts) >= 2:
                        H[k] = parts[1]
                        break
            if k in H:
                break

    # sample mass (mg)
    sample_mass_mg = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["size_mg"]):
            m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*mg', ln, flags=re.I)
            if m:
                sample_mass_mg = float(m.group(1))
                break

    # heating rate from header: "Ramp X.XX C/min"
    heating_rate_header = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["orgmethod"]):
            m = re.search(r'Ramp\s+([0-9]+(?:\.[0-9]+)?)\s*C\s*/\s*min', ln, flags=re.I)
            if m:
                heating_rate_header = float(m.group(1))
                break

    # data parse (expect ≥3 cols: Time, Temp, HeatFlow)
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
        "sample_mass_mg": sample_mass_mg,
        "operator": H.get("operator", ""),
        "file": H.get("file", ""),
        "heating_rate_header": heating_rate_header,
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

    # run-length blocks
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
    """Compute °C/min by linear regression (robust)."""
    if df.empty or len(df) < 10:
        return None
    t = df["Time"].to_numpy()
    T = df["Temp"].to_numpy()
    q10, q90 = np.quantile(np.arange(len(T)), [0.1, 0.9]).astype(int)
    if q90 <= q10:
        return None
    tt = t[q10:q90]
    TT = T[q10:q90]
    A = np.vstack([tt, np.ones_like(tt)]).T
    m, _ = np.linalg.lstsq(A, TT, rcond=None)[0]  # °C per time_unit (TA export usually minutes)
    return float(m)

def baseline_area(T, Y, a, b):
    m = (T >= a) & (T <= b)
    if not np.any(m):
        return np.nan
    x = T[m]; y = Y[m]
    y0, y1 = y[0], y[-1]; x0, x1 = x[0], x[-1]
    base = y0 + (y1 - y0) * (x - x0) / (x1 - x0 + 1e-12)
    return float(np.trapz(y - base, x))

def peak_in_window(T, Y, a, b, mode="min"):
    m = (T >= a) & (T <= b)
    if not np.any(m):
        return np.nan
    idx = np.nanargmin(Y[m]) if mode == "min" else np.nanargmax(Y[m])
    return float(T[m][idx])

def endotherm_is_down(T, Y, a, b):
    m = (T >= a) & (T <= b)
    if not np.any(m):
        return True
    seg = Y[m]
    return abs(np.nanmin(seg)) >= abs(np.nanmax(seg))

def tg_inflection(T, Y, a, b):
    m = (T >= a) & (T <= b)
    if not np.any(m):
        return np.nan
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
        return {"tg": (70, 110), "hm": (240, 300), "hc": (150, 220), "hcc": (None, None)}
    return {"tg": (50, 200), "hm": (150, 400), "hc": (80, 300), "hcc": (None, None)}

def compute_typeIII(df_all, H1, C, H2, material, dh0, polymer_frac):
    R = default_ranges(material)
    Tg = Tm = Tc = np.nan
    dHm = dHc = np.nan
    dHcc = 0.0

    # Tg, Tm, ΔHm → 2nd heating preferred
    if not H2.empty:
        T2 = H2["Temp"].to_numpy(); Y2 = H2["HeatFlow"].to_numpy()
        Tg = tg_inflection(T2, Y2, *R["tg"])
        hm_down = endotherm_is_down(T2, Y2, *R["hm"])
        Tm = peak_in_window(T2, Y2, *R["hm"], mode=("min" if hm_down else "max"))
        dHm = abs(baseline_area(T2, Y2, *R["hm"]))
    else:
        T = df_all["Temp"].to_numpy(); Y = df_all["HeatFlow"].to_numpy()
        Tg = tg_inflection(T, Y, *R["tg"])
        hm_down = endotherm_is_down(T, Y, *R["hm"])
        Tm = peak_in_window(T, Y, *R["hm"], mode=("min" if hm_down else "max"))
        dHm = abs(baseline_area(T, Y, *R["hm"]))

    # Tc, ΔHc → cooling
    if not C.empty:
        Tc = peak_in_window(C["Temp"].to_numpy(), C["HeatFlow"].to_numpy(), *R["hc"], mode="min")
        dHc = baseline_area(C["Temp"].to_numpy(), C["HeatFlow"].to_numpy(), *R["hc"])

    # ΔHcc → 1st heating (if present)
    if not H1.empty and all(v is not None for v in R["hcc"]):
        dHcc = abs(baseline_area(H1["Temp"].to_numpy(), H1["HeatFlow"].to_numpy(), *R["hcc"]))

    corr = dHm - dHcc
    denom = dh0 * max(polymer_frac, 1e-6)
    Xc = (corr / denom) * 100.0 if denom > 0 else np.nan

    def clean(x):
        return None if (x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))) else round(float(x), 2)

    return {
        "Tg (°C)": clean(Tg),
        "Tm (°C)": clean(Tm),
        "Tc (°C)": clean(Tc),
        "ΔHm (J/g)": clean(dHm),
        "ΔHcc (J/g)": clean(dHcc),
        "ΔHc (J/g)": clean(dHc),
        "Crystallinity Xc (%)": clean(Xc),
        "_note": "Tg/Tm/ΔHm from 2nd heating (fallback: all data); Tc/ΔHc from cooling; ΔHcc from 1st heating.",
    }

# ---------------- State ----------------------
st.title("DSC Library")

if "dsc_files" not in st.session_state:
    st.session_state["dsc_files"] = {}   # Library: key -> {orig_name,user_name,uploader,uploaded_at,bytes}
if "pending_uploads" not in st.session_state:
    st.session_state["pending_uploads"] = []  # staged before adding to library
if "seen_upload_ids" not in st.session_state:
    st.session_state["seen_upload_ids"] = set()  # MD5 dedup for staged files

# ---------------- Upload (Form + Submit + Dedup) ---------------------
st.header("Upload")

with st.form("uploader_form"):
    new_files = st.file_uploader(
        "Upload DSC .txt files",
        type=["txt"],
        accept_multiple_files=True,
        key="dsc_uploader"
    )
    staged = st.form_submit_button("Stage files")

if staged and new_files:
    added = 0
    for f in new_files:
        content = f.getvalue()
        fid = hashlib.md5(content + f.name.encode("utf-8")).hexdigest()
        if fid in st.session_state["seen_upload_ids"]:
            continue  # already staged → skip
        st.session_state["seen_upload_ids"].add(fid)
        st.session_state["pending_uploads"].append({
            "tmp_key": uuid.uuid4().hex,
            "file_id": fid,
            "orig_name": f.name,
            "bytes": content,
            "user_name": f.name  # default editable display name
        })
        added += 1
    if added:
        st.success(f"{added} file(s) staged. Name them below, then add to library.")
    # clear uploader widget & rerun to prevent re-staging on every rerun
    st.session_state.pop("dsc_uploader", None)
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()

# ----------- Pre-naming & Add to Library -----
if st.session_state["pending_uploads"]:
    st.subheader("Name your upload(s)")

    top_l, top_r = st.columns([4, 3])
    with top_l:
        st.caption("Give a user-friendly name, then add to your library.")
    with top_r:
        if st.button("Add ALL to Library"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in st.session_state["pending_uploads"]:
                key = uuid.uuid4().hex
                st.session_state["dsc_files"][key] = {
                    "orig_name": item["orig_name"],
                    "user_name": item["user_name"],
                    "uploader": current_user,
                    "uploaded_at": now,
                    "bytes": item["bytes"],
                }
                st.session_state["seen_upload_ids"].discard(item.get("file_id", ""))
            st.session_state["pending_uploads"].clear()
            st.success("All files added to library.")
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()

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
                "orig_name": item["orig_name"],
                "user_name": item["user_name"],
                "uploader": current_user,
                "uploaded_at": now,
                "bytes": item["bytes"],
            }
            st.session_state["seen_upload_ids"].discard(item.get("file_id", ""))
            remove_keys.append(item["tmp_key"])
    if remove_keys:
        st.session_state["pending_uploads"] = [x for x in st.session_state["pending_uploads"] if x["tmp_key"] not in remove_keys]
        st.success("Added to library.")
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

# ---------------- Uploaded List --------------
st.header("Uploaded DSC Files")
if not st.session_state["dsc_files"]:
    st.info("No files in library yet. Upload above, name them, then click Add to Library.")
else:
    for key, rec in list(st.session_state["dsc_files"].items()):
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 1])
        c1.write(rec["orig_name"])
        c2.write(rec["user_name"])
        c3.write(rec["uploader"])
        c4.write(rec["uploaded_at"])
        if c5.button("Delete", key=f"del_{key}"):
            del st.session_state["dsc_files"][key]
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()

# ---------------- Selection ------------------
st.header("Select a file to analyze")

def file_label(key: str) -> str:
    rec = st.session_state["dsc_files"][key]
    return f"{rec['user_name']} ({rec['orig_name']})"

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

    # segment split + heating rate validation
    H1, C, H2 = run_split(df)
    hr_calc_candidates = []
    for seg in [H1, H2]:
        r = calc_heating_rate(seg)
        if r is not None and r > 0:
            hr_calc_candidates.append(r)
    hr_calc = float(np.median(hr_calc_candidates)) if hr_calc_candidates else calc_heating_rate(df)

    # top metrics
    st.subheader("")
    m1, m2, m3 = st.columns(3)
    m1.metric("Sample Mass (mg)", f"{meta.get('sample_mass_mg') if meta.get('sample_mass_mg') is not None else '—'}")
    hr_show = meta.get("heating_rate_header")
    m2.metric("Heating Rate (°C/min)", f"{(hr_show if hr_show is not None else (round(hr_calc, 2) if hr_calc else '—'))}")
    m3.metric("Operator", meta.get("operator") or "—")

    # mismatch warning
    if meta.get("heating_rate_header") and hr_calc:
        if abs(hr_calc - meta["heating_rate_header"]) / max(meta["heating_rate_header"], 1e-6) > 0.10:
            st.warning(f"Header HR={meta['heating_rate_header']:.2f} °C/min, Calculated HR={hr_calc:.2f} °C/min (check program).")

    # Raw data (with units) + download
    st.subheader("Raw Data")
    df_disp = df.rename(columns={"Time": "Time (min)", "Temp": "Temperature (°C)", "HeatFlow": "Heat Flow (W/g)"})
    st.dataframe(df_disp, use_container_width=True, height=300)
    st.download_button(
        "⬇️ Download raw data (CSV)",
        df_disp.to_csv(index=False).encode("utf-8"),
        file_name=f"{(meta.get('sample_name') or 'sample')}_raw.csv",
        mime="text/csv",
    )

    # DSC curve (single, downloadable via modebar)
    st.subheader("DSC Curve with Analysis")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Temp"], y=df["HeatFlow"], mode="lines", name="DSC"))
    fig.update_layout(xaxis_title="Temperature (°C)", yaxis_title="Heat Flow (W/g)", legend_title="")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "toImageButtonOptions": {"format": "png"}})

    # Results — single block (Type III logic)
    st.subheader("Calculated Results (Type III)")
    results = compute_typeIII(df, H1, C, H2, material, dh0, polymer_frac)
    show = {k: v for k, v in results.items() if not k.startswith("_")}
    st.dataframe(pd.DataFrame(show, index=["Result"]), use_container_width=True)

    # short summary line
    order = ["Tg (°C)", "Tm (°C)", "Tc (°C)", "ΔHm (J/g)", "ΔHcc (J/g)", "ΔHc (J/g)", "Crystallinity Xc (%)"]
    items = []
    for k in order:
        if show.get(k) is not None:
            label = k.replace(" (°C)", "").replace(" (J/g)", "")
            items.append(f"{label} = {show[k]}")
    st.info(";  ".join(items) if items else "No calculable result in the default ranges.")
    st.caption(f"{results.get('_note','')}  ΔH°={dh0:.1f} J/g; polymer fraction={polymer_frac:.2f}.")
else:
    st.info("Select a file to analyze.")
