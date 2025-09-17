import streamlit as st
import pandas as pd
import os
import io
import shutil
from pathlib import Path
from datetime import datetime
from typing import List

# =========================
# Sayfa / Erişim Ayarları
# =========================
st.set_page_config(page_title="SEM & EDS Library", page_icon="🧪", layout="wide")

# (Uygulamanızda giriş kontrolü varsa, DSC/Production ile uyumlu tutalım)
if "authenticated" in st.session_state and not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.title("SEM & EDS Library")

# =========================
# Kalıcı Depo
# =========================
BASE_DIR = Path("sem_eds_uploads")
RECORDS_CSV = Path("sem_eds_records.csv")
BASE_DIR.mkdir(exist_ok=True, parents=True)

RECORD_COLUMNS = [
    "entry_id",          # benzersiz klasör adı
    "production_name",
    "project_name",      # CREDIT / COMPADDITIVE
    "producer",
    "sample_no",
    "test_date",         # YYYY-MM-DD
    "sem_files",         # ; ile ayrılmış göreli yollar
    "eds_files",         # ; ile ayrılmış göreli yollar
    "created_at",
]

def load_records() -> pd.DataFrame:
    if RECORDS_CSV.exists():
        df = pd.read_csv(RECORDS_CSV)
        # Eksik kolonlar olursa düzelt
        for c in RECORD_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df = df[RECORD_COLUMNS]
        return df
    else:
        return pd.DataFrame(columns=RECORD_COLUMNS)

def save_records(df: pd.DataFrame):
    df.to_csv(RECORDS_CSV, index=False)

def safe_name(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s) or "entry"

def bytes_from_file(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()

records_df = load_records()

# =========================
# Yeni Kayıt Formu
# =========================
st.subheader("➕ Create New SEM & EDS Entry")

with st.form("sem_eds_form", clear_on_submit=True):
    c1, c2 = st.columns([1, 1])
    with c1:
        production_name = st.text_input("Production Name", placeholder="e.g. Sample Batch #45")
        producer = st.text_input("Producer", placeholder="e.g. Zeynep Ege Uysal")
        sample_no = st.text_input("Sample No.", placeholder="e.g. SEM-EDS-001")
    with c2:
        project_name = st.radio("Project Name", ["CREDIT", "COMPADDITIVE"], horizontal=True)
        test_date = st.date_input("Test Date", value=datetime.now().date(), format="YYYY-MM-DD")

    st.markdown("**SEM Files Upload** (multiple)")
    sem_files = st.file_uploader(
        "Upload SEM files (images or PDFs)",
        type=["png", "jpg", "jpeg", "tif", "tiff", "bmp", "pdf"],
        accept_multiple_files=True,
        key="sem_uploader",
        label_visibility="collapsed",
    )

    st.markdown("**EDS Files Upload** (multiple)")
    eds_files = st.file_uploader(
        "Upload EDS files (csv, txt, xlsx, pdf, docx)",
        type=["csv", "txt", "xlsx", "pdf", "docx"],
        accept_multiple_files=True,
        key="eds_uploader",
        label_visibility="collapsed",
    )

    submitted = st.form_submit_button("💾 Save Entry", type="primary")

if submitted:
    # Gerekli minimum doğrulama
    if not production_name:
        st.error("❗ Production Name is required.")
    else:
        entry_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        entry_dir = BASE_DIR / f"{safe_name(production_name)}_{entry_id}"
        sem_dir = entry_dir / "SEM"
        eds_dir = entry_dir / "EDS"
        sem_dir.mkdir(parents=True, exist_ok=True)
        eds_dir.mkdir(parents=True, exist_ok=True)

        saved_sem_paths: List[Path] = []
        for f in sem_files or []:
            fp = sem_dir / safe_name(f.name)
            with open(fp, "wb") as out:
                out.write(f.getbuffer())
            saved_sem_paths.append(fp.relative_to(BASE_DIR))

        saved_eds_paths: List[Path] = []
        for f in eds_files or []:
            fp = eds_dir / safe_name(f.name)
            with open(fp, "wb") as out:
                out.write(f.getbuffer())
            saved_eds_paths.append(fp.relative_to(BASE_DIR))

        new_row = {
            "entry_id": entry_dir.name,
            "production_name": production_name,
            "project_name": project_name,
            "producer": producer,
            "sample_no": sample_no,
            "test_date": str(test_date),
            "sem_files": ";".join(str(p) for p in saved_sem_paths),
            "eds_files": ";".join(str(p) for p in saved_eds_paths),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        records_df = pd.concat([records_df, pd.DataFrame([new_row])], ignore_index=True)
        save_records(records_df)
        st.success("✅ Entry saved successfully.")
        st.rerun()

# =========================
# Kayıtların Listesi
# =========================
st.markdown("---")
st.subheader("All SEM & EDS Records")

if records_df.empty:
    st.info("No records yet.")
else:
    # Sondan başa doğru (yeni en üstte)
    for _, row in records_df.sort_values("created_at", ascending=False).iterrows():
        title_left = row["production_name"] or "—"
        title_right = row["project_name"] or ""
        expander = st.expander(f"{title_left} ({title_right})", expanded=False)

        with expander:
            cA, cB, cC = st.columns([1, 1, 1])
            with cA:
                st.markdown(f"**Producer:** {row['producer'] or '—'}")
                st.markdown(f"**Sample No.:** {row['sample_no'] or '—'}")
            with cB:
                st.markdown(f"**Test Date:** {row['test_date'] or '—'}")
                st.markdown(f"**Created At:** {row['created_at'] or '—'}")
            with cC:
                sem_list = [Path(BASE_DIR) / Path(p) for p in (row["sem_files"].split(";") if str(row["sem_files"]) else [])]
                eds_list = [Path(BASE_DIR) / Path(p) for p in (row["eds_files"].split(";") if str(row["eds_files"]) else [])]
                st.markdown(f"**SEM Files:** {len(sem_list)}")
                st.markdown(f"**EDS Files:** {len(eds_list)}")

            st.markdown("—")
            # SEM dosyaları: küçük önizleme + indirme
            if sem_list:
                st.markdown("**SEM Files**")
                for p in sem_list:
                    cols = st.columns([3, 1])
                    try:
                        if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]:
                            cols[0].image(str(p), caption=p.name, use_container_width=True)
                        else:
                            cols[0].write(p.name)
                    except Exception as e:
                        cols[0].warning(f"Preview error: {e}")

                    with open(p, "rb") as fh:
                        cols[1].download_button(
                            "⬇️ Download",
                            data=fh.read(),
                            file_name=p.name,
                            mime=None,
                            key=f"dl_sem_{row['entry_id']}_{p.name}",
                        )

            # EDS dosyaları: liste + indirme (CSV/TXT küçük tablo önizleme)
            if eds_list:
                st.markdown("**EDS Files**")
                for p in eds_list:
                    cols = st.columns([3, 1])
                    shown = False
                    try:
                        if p.suffix.lower() in [".csv", ".txt"]:
                            df_preview = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_csv(p, sep=None, engine="python")
                            cols[0].dataframe(df_preview.head(20), use_container_width=True)
                            shown = True
                    except Exception:
                        pass
                    if not shown:
                        cols[0].write(p.name)

                    with open(p, "rb") as fh:
                        cols[1].download_button(
                            "⬇️ Download",
                            data=fh.read(),
                            file_name=p.name,
                            mime=None,
                            key=f"dl_eds_{row['entry_id']}_{p.name}",
                        )

            st.markdown("—")
            # Silme butonu
            del_col = st.columns([1, 4])[0]
            if del_col.button("🗑️ Delete This Entry", key=f"del_{row['entry_id']}"):
                # Klasörü ve kayıt satırını sil
                try:
                    shutil.rmtree(BASE_DIR / row["entry_id"], ignore_errors=True)
                except Exception as e:
                    st.error(f"Folder delete error: {e}")

                new_df = records_df.loc[records_df["entry_id"] != row["entry_id"]].reset_index(drop=True)
                save_records(new_df)
                st.success("Entry deleted.")
                st.rerun()

