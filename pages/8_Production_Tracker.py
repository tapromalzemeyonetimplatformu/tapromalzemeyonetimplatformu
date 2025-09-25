# 8_Production_Tracker.py
import os
import sqlite3
from datetime import datetime, date
import streamlit as st
import pandas as pd

# ✅ Kullanıcı giriş kontrolü
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

# ===============================
# Helpers: Auth / Paths / DB
# ===============================
APP_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(APP_DATA_DIR, "production_tracker.db")

def _as_str(x):
    """Return a clean string for potential username-like values."""
    if x is None:
        return ""
    if isinstance(x, (list, tuple, set)):
        return " ".join(map(str, x)).strip()
    if isinstance(x, dict):
        # common auth dict shapes
        for k in ("username", "name", "display_name", "email", "user", "id"):
            if k in x and str(x[k]).strip():
                return str(x[k]).strip()
        return ""
    return str(x).strip()

def current_username() -> str:
    """
    Try common session_state keys used by Streamlit auth patterns.
    Falls back from display name to username to email; never returns 'unknown'
    if a plausible value exists.
    """
    cand_keys = [
        "name",                 # streamlit-authenticator display name
        "username",             # streamlit-authenticator username
        "user",                 # generic
        "current_user",         # custom apps
        "auth_username",        # custom
        "user_name",            # occasional variant
        "profile",              # might be a dict
        "account",              # might be a dict
        "email",                # sometimes used as id
    ]
    candidates = []
    for k in cand_keys:
        if k in st.session_state:
            candidates.append(_as_str(st.session_state.get(k)))

    # Also inspect nested dicts if present under common containers
    nested_sources = [st.session_state.get("auth"), st.session_state.get("user_info")]
    for src in nested_sources:
        s = _as_str(src)
        if s:
            candidates.append(s)

    for c in candidates:
        if c:  # first non-empty
            return c

    return "unknown"

def get_conn():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at_utc TEXT NOT NULL,
            created_by TEXT NOT NULL,
            raw_material TEXT NOT NULL,
            direction_angle TEXT NOT NULL,
            project_name TEXT NOT NULL,            -- CREDIT / COMPADDITIVE
            producer_name TEXT NOT NULL,
            supplier_name TEXT NOT NULL,
            printing_machine TEXT NOT NULL,
            technology TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            production_date TEXT NOT NULL,         -- ISO 'YYYY-MM-DD'
            tests_planned_done TEXT NOT NULL,
            process_parameters TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn

def add_entry(
    raw_material: str,
    direction_angle: str,
    project_name: str,
    producer_name: str,
    supplier_name: str,
    printing_machine: str,
    technology: str,
    sample_count: int,
    production_date: date,
    tests_planned_done: str,
    process_parameters: str,
):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO production_entries
        (created_at_utc, created_by, raw_material, direction_angle, project_name,
         producer_name, supplier_name, printing_machine, technology, sample_count,
         production_date, tests_planned_done, process_parameters)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(timespec="seconds"),
            current_username(),
            raw_material.strip(),
            direction_angle.strip(),
            project_name.strip(),
            producer_name.strip(),
            supplier_name.strip(),
            printing_machine.strip(),
            technology.strip(),
            int(sample_count),
            production_date.isoformat(),
            tests_planned_done.strip(),
            process_parameters.strip(),
        ),
    )
    conn.commit()

def list_entries() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT
            id,
            production_date AS "Production Date",
            raw_material AS "Raw Material",
            direction_angle AS "Direction & Angle",
            project_name AS "Project Name",
            producer_name AS "Producer Name",
            supplier_name AS "Supplier Name",
            printing_machine AS "Printing Machine",
            technology AS "Technology",
            sample_count AS "Sample Count",
            tests_planned_done AS "Tests Planned/Done",
            process_parameters AS "Process Parameters",
            created_by AS "Uploader",
            created_at_utc AS "Created At (UTC)"
        FROM production_entries
        ORDER BY date(production_date) DESC, id DESC
        """,
        conn,
    )
    return df

def delete_entry(row_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM production_entries WHERE id = ?", (row_id,))
    conn.commit()

# ===============================
# UI: Page
# ===============================
st.set_page_config(page_title="Production Tracker", page_icon="📘", layout="wide")
st.title("📘 Production Tracker")

init_db()

with st.expander("➕ Create New Production Record", expanded=True):
    with st.form("production_form", clear_on_submit=True):
        # NOTE: Order matches your requested list exactly
        col1, col2, col3 = st.columns(3)
        with col1:
            raw_material = st.text_input("Raw Material (e.g. PEEK)", placeholder="PEEK")
            project_name = st.selectbox(
                "Project Name (CREDIT/COMPADDITIVE)", options=["CREDIT", "COMPADDITIVE"]
            )
            supplier_name = st.text_input("Supplier Name (e.g. INTAMSYS)", placeholder="INTAMSYS")
            technology = st.text_input("Technology (e.g. FDM)", placeholder="FDM")
            production_date = st.date_input(
                "Production Date", value=date.today(), format="YYYY-MM-DD"
            )
        with col2:
            direction_angle = st.text_input(
                "Direction and Angle (e.g. ZX 45°)", placeholder="ZX 45°"
            )
            producer_name = st.text_input(
                "Producer Name (e.g. Necip Hayran)", placeholder="Necip Hayran"
            )
            printing_machine = st.text_input("Printing Machine (e.g. 610)", placeholder="610")
            sample_count = st.number_input("Sample Count", min_value=1, step=1, value=1)
            tests_planned_done = st.text_area(
                "Tests Planned/Done",
                placeholder="e.g. DSC, Tensile done; SEM planned",
                height=96,
            )
        with col3:
            process_parameters = st.text_area(
                "Process Parameters",
                placeholder=(
                    "Key settings, temperatures, speeds, environment, orientation, etc.\n"
                    "Example:\n"
                    "- Nozzle 385°C, Bed 150°C, Chamber 90°C\n"
                    "- Layer 0.2 mm, Infill 100%, Speed 25 mm/s\n"
                    "- Orientation ZX 45°, Anneal 200°C 2h"
                ),
                height=220,
            )

        submitted = st.form_submit_button("Save Record", use_container_width=True)
        if submitted:
            required_fields = {
                "Raw Material": raw_material,
                "Direction and Angle": direction_angle,
                "Producer Name": producer_name,
                "Supplier Name": supplier_name,
                "Printing Machine": printing_machine,
                "Technology": technology,
            }
            missing = [k for k, v in required_fields.items() if not str(v).strip()]
            if missing:
                st.error("Please fill required fields: " + ", ".join(missing))
            else:
                try:
                    add_entry(
                        raw_material=raw_material,
                        direction_angle=direction_angle,
                        project_name=project_name,
                        producer_name=producer_name,
                        supplier_name=supplier_name,
                        printing_machine=printing_machine,
                        technology=technology,
                        sample_count=int(sample_count),
                        production_date=production_date,
                        tests_planned_done=tests_planned_done,
                        process_parameters=process_parameters,
                    )
                    st.success("Record saved successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save record: {e}")

st.subheader("📋 Records")
df = list_entries()

# Optional quick filters
with st.expander("🔎 Filters", expanded=False):
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        proj_filter = st.multiselect("Project Name", options=sorted(df["Project Name"].unique()))
    with fcol2:
        tech_filter = st.multiselect("Technology", options=sorted(df["Technology"].unique()))
    with fcol3:
        rm_filter = st.multiselect("Raw Material", options=sorted(df["Raw Material"].unique()))
    with fcol4:
        uploader_filter = st.multiselect("Uploader", options=sorted(df["Uploader"].unique()))

    mask = pd.Series([True] * len(df))
    if proj_filter:
        mask &= df["Project Name"].isin(proj_filter)
    if tech_filter:
        mask &= df["Technology"].isin(tech_filter)
    if rm_filter:
        mask &= df["Raw Material"].isin(rm_filter)
    if uploader_filter:
        mask &= df["Uploader"].isin(uploader_filter)
    df = df[mask].reset_index(drop=True)

# Show table with delete buttons
if df.empty:
    st.info("No records yet.")
else:
    # Add a delete column with buttons
    action_col = "Delete"
    df_show = df.copy()
    df_show[action_col] = ""

    # Render table row by row with delete buttons
    for i, row in df_show.iterrows():
        with st.container(border=True):
            top_cols = st.columns([1.2, 1.2, 1.1, 1.1, 1, 1, 1])
            with top_cols[0]:
                st.markdown(f"**Production Date:** {row['Production Date']}")
                st.markdown(f"**Raw Material:** {row['Raw Material']}")
            with top_cols[1]:
                st.markdown(f"**Direction & Angle:** {row['Direction & Angle']}")
                st.markdown(f"**Project Name:** {row['Project Name']}")
            with top_cols[2]:
                st.markdown(f"**Producer Name:** {row['Producer Name']}")
                st.markdown(f"**Supplier Name:** {row['Supplier Name']}")
            with top_cols[3]:
                st.markdown(f"**Printing Machine:** {row['Printing Machine']}")
                st.markdown(f"**Technology:** {row['Technology']}")
            with top_cols[4]:
                st.markdown(f"**Sample Count:** {row['Sample Count']}")
                st.markdown(f"**Uploader:** {row['Uploader'] if row['Uploader'] != 'unknown' else '-'}")
            with top_cols[5]:
                st.markdown(f"**Created At (UTC):** {row['Created At (UTC)']}")
            with top_cols[6]:
                if st.button("Delete", key=f"del_{int(df.loc[i, 'id'])}", type="secondary"):
                    try:
                        delete_entry(int(df.loc[i, "id"]))
                        st.toast("Deleted.", icon="🗑️")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

            # Full-width text areas for long fields
            st.markdown("**Tests Planned/Done**")
            st.code(str(row["Tests Planned/Done"]).strip() or "-", language="markdown")
            st.markdown("**Process Parameters**")
            st.code(str(row["Process Parameters"]).strip() or "-", language="markdown")

