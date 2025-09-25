# 5_DSC_Library.py — DSC Library (final)
# - Upload → Stage (md5 dedup) → Name → Add to Library
# - Robust H1/C/H2 segmentation with safe fallbacks
# - Heat Flow Unit selector (default **mW**); hesaplarda daima W/g kullanılır
# - ΔH = ∫(W/g) dT / β(°C/s); Type III öncelikli: H2→(Tg,Tm,ΔHm), C→(Tc,ΔHc), H1→(ΔHcc)
# - PEKK pencereleri düzeltildi: Tg(150–170), Hm(295–360), Hc(200–270), Hcc(180–260)
# - Grafikte & tabloda Heat Flow mW (arka plan beyaz)

import io, re, math, uuid, hashlib
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="DSC Library", page_icon="🔥", layout="wide")

# ---------------- Utils ----------------
def do_rerun():
    try: st.rerun()
    except Exception: pass

def r2(x):
    return None if (x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))) else round(float(x), 2)

# ---------------- Auth ----------------
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

# --------------- Constants ---------------
POLYMER_DH0_DEFAULTS = {"PEEK": 130.0, "PEKK": 130.0, "PPS": 112.0}
HEADER_KEYS = {
    "sample": ["Sample", "Sample Name"],
    "size_mg": ["Size", "Sample mass", "Mass", "Weight"],
    "orgmethod": ["OrgMethod", "Method", "Program"],
    "operator": ["Operator"],
    "file": ["File", "OrgFile"],
}

def default_ranges(material: str):
    m = (material or "").upper()
    if m.startswith("PEKK"):
        # düzeltildi
        return {"tg": (150, 170), "hm": (295, 360), "hc": (200, 270), "hcc": (180, 260)}
    if m.startswith("PEEK"):
        return {"tg": (120, 170), "hm": (300, 385), "hc": (180, 280), "hcc": (150, 260)}
    if m.startswith("PPS"):
        return {"tg": (70, 110), "hm": (240, 300), "hc": (150, 220), "hcc": (None, None)}
    return {"tg": (50, 200), "hm": (150, 400), "hc": (80, 300), "hcc": (None, None)}

# --------------- Parse .txt ---------------
def parse_header_and_data(text: str):
    lines = text.splitlines()
    # first numeric line = data start
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

    sample_mass_mg = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["size_mg"]):
            m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*mg', ln, flags=re.I)
            if m: sample_mass_mg = float(m.group(1)); break

    heating_rate_header = None
    for ln in header:
        if any(ln.strip().startswith(kw) for kw in HEADER_KEYS["orgmethod"]):
            m = re.search(r'Ramp\s+([0-9]+(?:\.[0-9]+)?)\s*C\s*/\s*min', ln, flags=re.I)
            if m: heating_rate_header = float(m.group(1)); break

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

# ----------- Segment (robust + fallback) -----------
def robust_segments(df: pd.DataFrame):
    if df.empty or len(df) < 50:
        return df.copy(), pd.DataFrame(), pd.DataFrame()
    T = df["Temp"].to_numpy()
    dT = np.diff(T, prepend=T[0])
    from scipy.ndimage import uniform_filter1d
    dTs = uniform_filter1d(dT, size=41, mode="nearest")
    sign = np.sign(dTs)

    blocks, start = [], 0
    for i in range(1, len(sign)):
        if sign[i] != sign[i-1]:
            if i-start>30: blocks.append((start,i))
            start=i
    if len(sign)-start>30: blocks.append((start,len(sign)))

    heats=[(a,b) for (a,b) in blocks if np.mean(dTs[a:b])>=0]
    cools=[(a,b) for (a,b) in blocks if np.mean(dTs[a:b])<0]

    H1=heats[0] if heats else None
    C=next(((a,b) for (a,b) in cools if H1 and a>H1[1]),None)
    H2=next(((a,b) for (a,b) in heats if C and a>C[1]),None)

    def sl(blk): return df.iloc[blk[0]:blk[1]].reset_index(drop=True) if blk else pd.DataFrame(columns=df.columns)

    if H2 is None and heats: H2=heats[-1]
    if C  is None and cools: C =cools[len(cools)//2] if len(cools)>1 else cools[0]
    if H1 is None and heats: H1=heats[0]
    return sl(H1),sl(C),sl(H2)

# ----------- Heating rate (segment-wise) -----------
def slope_beta_C_per_min(df):
    if df.empty or len(df)<10: return None
    t=df["Time"].to_numpy(); T=df["Temp"].to_numpy()
    q10,q90=np.quantile(np.arange(len(T)),[0.1,0.9]).astype(int)
    if q90<=q10: return None
    tt=t[q10:q90]; TT=T[q10:q90]
    A=np.vstack([tt,np.ones_like(tt)]).T
    m,_=np.linalg.lstsq(A,TT,rcond=None)[0]
    return float(m)  # °C/min

# ----------- Unit transforms -----------
def wpg_from_raw(D: pd.DataFrame, sample_mass_mg: float, mode: str):
    """
    mode:
      - 'mw'  : raw is mW (total power). W/g = (mW/1000)/mass_g
      - 'wpg' : raw already W/g
    """
    if D.empty or sample_mass_mg is None or sample_mass_mg <= 0:
        return None, None
    mass_g = sample_mass_mg/1000.0
    HF = D["HeatFlow"].to_numpy().astype(float)
    if mode == "mw":
        Y_Wpg = (HF/1000.0)/mass_g
    else:
        Y_Wpg = HF
    T = D["Temp"].to_numpy()
    return T, Y_Wpg

def to_mw_for_display(Y_Wpg: np.ndarray, mass_mg: float):
    return Y_Wpg * (mass_mg/1000.0) * 1000.0

# ----------- Math helpers -----------
def line_baseline(x,y):
    y0,y1=y[0],y[-1]; x0,x1=x[0],x[-1]
    return y0+(y1-y0)*(x-x0)/(x1-x0+1e-12)

def area_J_per_g_over_T(T,Y_Wpg,a,b,beta_C_per_s):
    m=(T>=a)&(T<=b)
    if not np.any(m) or not beta_C_per_s or beta_C_per_s<=0: return np.nan
    x=T[m]; y=Y_Wpg[m]
    base=line_baseline(x,y)
    area_Wpg_degC=float(np.trapz(y-base,x))
    return area_Wpg_degC/beta_C_per_s

def peak_T(T,Y,a,b,mode="min"):
    m=(T>=a)&(T<=b)
    if not np.any(m): return np.nan
    idx=np.nanargmin(Y[m]) if mode=="min" else np.nanargmax(Y[m])
    return float(T[m][idx])

def endo_is_down(T,Y,a,b):
    m=(T>=a)&(T<=b)
    if not np.any(m): return True
    seg=Y[m]; return abs(np.nanmin(seg))>=abs(np.nanmax(seg))

def tg_inflection(T,Y,a,b):
    m=(T>=a)&(T<=b)
    if not np.any(m): return np.nan
    from scipy.ndimage import gaussian_filter1d
    x=T[m]; y=gaussian_filter1d(Y[m],sigma=7)
    dy=np.gradient(y,x); idx=np.nanargmax(np.abs(dy))
    return float(x[idx])

# ----------- Core computation -----------
def compute_typeIII(meta, df_all, H1, C, H2, material, dh0, polymer_frac, beta_hdr_or_est, unit_choice):
    R=default_ranges(material)
    mass_mg=meta.get("sample_mass_mg")

    # β per segment (fallback header/overall)
    beta_H2=slope_beta_C_per_min(H2) or beta_hdr_or_est
    beta_C =slope_beta_C_per_min(C)  or beta_hdr_or_est
    beta_H1=slope_beta_C_per_min(H1) or beta_hdr_or_est

    # unit mode: default mW (kullanıcı seçimi)
    chosen = "mw" if unit_choice=="mW" else ("wpg" if unit_choice=="W/g" else "mw")

    res={"Tg (°C)":None,"Tm (°C)":None,"Tc (°C)":None,
         "ΔHm (J/g)":None,"ΔHcc (J/g)":None,"ΔHc (J/g)":None,
         "Crystallinity Xc (%)":None,"_chosen_unit":chosen}

    # H2 → Tg, Tm, ΔHm
    if not H2.empty and mass_mg:
        T2,Y2=wpg_from_raw(H2,mass_mg,chosen)
        if T2 is not None:
            res["Tg (°C)"]=r2(tg_inflection(T2,Y2,*R["tg"]))
            hm_down=endo_is_down(T2,Y2,*R["hm"])
            res["Tm (°C)"]=r2(peak_T(T2,Y2,*R["hm"],mode=("min" if hm_down else "max")))
            beta_s=(beta_H2 or 0)/60.0 if beta_H2 else None
            dHm=area_J_per_g_over_T(T2,Y2,*R["hm"],beta_s)
            if not (dHm is None or math.isnan(dHm)): res["ΔHm (J/g)"]=r2(abs(dHm))

    # C → Tc, ΔHc
    if not C.empty and mass_mg:
        TcT,TcY=wpg_from_raw(C,mass_mg,chosen)
        if TcT is not None:
            res["Tc (°C)"]=r2(peak_T(TcT,TcY,*R["hc"],mode="min"))
            beta_s=(beta_C or 0)/60.0 if beta_C else None
            dHc=area_J_per_g_over_T(TcT,TcY,*R["hc"],beta_s)
            if not (dHc is None or math.isnan(dHc)): res["ΔHc (J/g)"]=r2(abs(dHc))

    # H1 → ΔHcc
    if not H1.empty and mass_mg and all(v is not None for v in R["hcc"]):
        T1,Y1=wpg_from_raw(H1,mass_mg,chosen)
        if T1 is not None:
            beta_s=(beta_H1 or 0)/60.0 if beta_H1 else None
            dHcc=area_J_per_g_over_T(T1,Y1,*R["hcc"],beta_s)
            if not (dHcc is None or math.isnan(dHcc)): res["ΔHcc (J/g)"]=r2(abs(dHcc))

    # Xc
    if res["ΔHm (J/g)"] is not None and dh0 and polymer_frac:
        corr = res["ΔHm (J/g)"] - (res["ΔHcc (J/g)"] or 0.0)
        res["Crystallinity Xc (%)"]=r2((corr/(dh0*polymer_frac))*100.0)

    betas_info={"β_H1":r2(beta_H1),"β_C":r2(beta_C),"β_H2":r2(beta_H2)}
    return res,betas_info

# ---------------- State ----------------------
st.title("DSC Library")
if "dsc_files" not in st.session_state: st.session_state["dsc_files"]={}
if "pending_uploads" not in st.session_state: st.session_state["pending_uploads"]=[]
if "seen_upload_ids" not in st.session_state: st.session_state["seen_upload_ids"]=set()

# ---------------- Upload ---------------------
st.header("Upload")
with st.form("uploader_form"):
    new_files=st.file_uploader("Upload DSC .txt files",type=["txt"],accept_multiple_files=True,key="dsc_uploader")
    staged=st.form_submit_button("Stage files")
if staged and new_files:
    added=0
    for f in new_files:
        content=f.getvalue()
        fid=hashlib.md5(content+f.name.encode()).hexdigest()
        if fid in st.session_state["seen_upload_ids"]: continue
        st.session_state["seen_upload_ids"].add(fid)
        st.session_state["pending_uploads"].append({
            "tmp_key":uuid.uuid4().hex,"file_id":fid,"orig_name":f.name,
            "bytes":content,"user_name":f.name
        }); added+=1
    if added: st.success(f"{added} file(s) staged. Name them below, then add to library.")
    st.session_state.pop("dsc_uploader",None); do_rerun()

# ----------- Pre-naming & Add to Library -----
if st.session_state["pending_uploads"]:
    st.subheader("Name your upload(s)")
    if st.button("Add ALL to Library"):
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in st.session_state["pending_uploads"]:
            key=uuid.uuid4().hex
            st.session_state["dsc_files"][key]={
                "orig_name":item["orig_name"],"user_name":item["user_name"],
                "uploader":current_user,"uploaded_at":now,"bytes":item["bytes"]
            }
            st.session_state["seen_upload_ids"].discard(item.get("file_id",""))
        st.session_state["pending_uploads"].clear(); do_rerun()

    remove_keys=[]
    for item in st.session_state["pending_uploads"]:
        c1,c2,c3=st.columns([4,4,1])
        c1.write(item["orig_name"])
        new_nm=c2.text_input("User Name",value=item["user_name"],key=f"pending_name_{item['tmp_key']}")
        item["user_name"]=new_nm
        if c3.button("Add to Library",key=f"add_{item['tmp_key']}"):
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            key=uuid.uuid4().hex
            st.session_state["dsc_files"][key]={
                "orig_name":item["orig_name"],"user_name":item["user_name"],
                "uploader":current_user,"uploaded_at":now,"bytes":item["bytes"]
            }
            st.session_state["seen_upload_ids"].discard(item.get("file_id",""))
            remove_keys.append(item["tmp_key"])
    if remove_keys:
        st.session_state["pending_uploads"]=[x for x in st.session_state["pending_uploads"] if x["tmp_key"] not in remove_keys]
        do_rerun()

# ---------------- Uploaded List --------------
st.header("Uploaded DSC Files")
if not st.session_state["dsc_files"]:
    st.info("No files in library yet. Upload above, name them, then click Add to Library.")
else:
    for key,rec in list(st.session_state["dsc_files"].items()):
        c1,c2,c3,c4,c5=st.columns([3,3,2,2,1])
        c1.write(rec["orig_name"]); c2.write(rec["user_name"])
        c3.write(rec["uploader"]); c4.write(rec["uploaded_at"])
        if c5.button("Delete",key=f"del_{key}"):
            del st.session_state["dsc_files"][key]; do_rerun()

# ---------------- Selection ------------------
st.header("Select a file to analyze")
def file_label(key:str)->str:
    rec=st.session_state["dsc_files"][key]; return f"{rec['user_name']} ({rec['orig_name']})"
options=list(st.session_state["dsc_files"].keys())
selected_key=st.selectbox("Choose a file",options=options,format_func=(file_label if options else None))
dsc_type=st.selectbox("Type",options=["Type III","Type II","Type I"],index=0)
material=st.selectbox("Material",options=["PEEK","PEKK","PPS","OTHER"],index=0)

# Unit selector (default mW)
unit_choice=st.selectbox("Heat Flow Unit",options=["mW","W/g"],index=0,
                         help="Raw 'Heat Flow' column unit. Display mW; calculations always use W/g.")

with st.expander("Advanced (ΔH° and polymer fraction)"):
    default_dh0=POLYMER_DH0_DEFAULTS.get(material,130.0)
    dh0=st.number_input("ΔH° (J/g)",value=float(default_dh0),step=1.0,format="%.2f")
    polymer_frac=st.number_input("Polymer mass fraction (1 − filler wt. fraction)",min_value=0.0,max_value=1.0,value=1.0,step=0.05)

# ---------------- Analysis -------------------
if selected_key:
    raw=st.session_state["dsc_files"][selected_key]["bytes"].decode("utf-8","ignore")
    meta,df=parse_header_and_data(raw)
    H1,C,H2=robust_segments(df)
    beta_hdr_or_est=meta.get("heating_rate_header") or slope_beta_C_per_min(df)

    # header cards
    m1,m2,m3=st.columns(3)
    m1.metric("Sample Mass (mg)",f"{meta.get('sample_mass_mg') if meta.get('sample_mass_mg') is not None else '—'}")
    m2.metric("Heating Rate (°C/min)",f"{r2(beta_hdr_or_est) if beta_hdr_or_est else '—'}")
    m3.metric("Operator",meta.get("operator") or "—")

    # results
    results,betas_info=compute_typeIII(meta,df,H1,C,H2,material,dh0,polymer_frac,beta_hdr_or_est,unit_choice)

    # Raw Data (display mW)
    st.subheader("Raw Data")
    if meta.get("sample_mass_mg"):
        T_all,Y_all=wpg_from_raw(df,meta["sample_mass_mg"],results["_chosen_unit"])
        HF_mW_display = to_mw_for_display(Y_all, meta["sample_mass_mg"]) if T_all is not None else df["HeatFlow"].to_numpy()
    else:
        HF_mW_display=df["HeatFlow"].to_numpy()
    df_disp=pd.DataFrame({"Time (min)":df["Time"],"Temperature (°C)":df["Temp"],"Heat Flow (mW)":HF_mW_display})
    st.dataframe(df_disp,use_container_width=True,height=300)
    st.download_button("⬇️ Download raw data (CSV)",df_disp.to_csv(index=False).encode("utf-8"),
                       file_name=f"{(meta.get('sample_name') or 'sample')}_raw.csv",mime="text/csv")

    # Plot
    st.subheader("DSC Curve with Analysis")
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=df["Temp"],y=HF_mW_display,mode="lines",name="DSC",
                             line=dict(width=3,color="#2563EB"),
                             hovertemplate="T=%{x:.2f} °C<br>HF=%{y:.2f} mW<extra></extra>"))
    fig.update_layout(xaxis_title="Temperature (°C)",yaxis_title="Heat Flow (mW)",
                      legend_title="",plot_bgcolor="#FFFFFF",paper_bgcolor="#FFFFFF",
                      xaxis=dict(showgrid=True,gridcolor="rgba(0,0,0,0.08)"),
                      yaxis=dict(showgrid=True,gridcolor="rgba(0,0,0,0.08)"),
                      margin=dict(l=40,r=20,t=10,b=40))
    st.plotly_chart(fig,use_container_width=True,config={"displaylogo":False,"toImageButtonOptions":{"format":"png"}})

    # Calculated Results
    st.subheader("Calculated Results (Type III)")
    show={k:v for k,v in results.items() if not k.startswith("_")}
    st.dataframe(pd.DataFrame(show,index=["Result"]),use_container_width=True)

    order=["Tg (°C)","Tm (°C)","Tc (°C)","ΔHm (J/g)","ΔHcc (J/g)","ΔHc (J/g)","Crystallinity Xc (%)"]
    items=[f"{k.replace(' (°C)','').replace(' (J/g)','')} = {results[k]}" for k in order if results.get(k) is not None]
    st.info(";  ".join(items) if items else "No calculable result in the default ranges.")
    st.caption(
        f"β(H1/C/H2) = {betas_info['β_H1']} / {betas_info['β_C']} / {betas_info['β_H2']} °C/min. "
        f"ΔH°={dh0:.1f} J/g; polymer fraction={polymer_frac:.2f}.  "
        f"Heat Flow mode = {results['_chosen_unit']}.  "
        "Computation: convert to W/g → baseline-corrected ∫(dT)/β.  "
        "Windows: PEKK hm 295–360 °C, hc 200–270 °C, hcc 180–260 °C."
    )
else:
    st.info("Select a file to analyze.")
