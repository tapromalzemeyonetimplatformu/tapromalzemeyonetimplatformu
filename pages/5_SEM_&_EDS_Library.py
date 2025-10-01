import streamlit as st
import pandas as pd
import os
import base64
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# =========================
# Sayfa / Erişim Ayarları
# =========================
st.set_page_config(page_title="SEM & EDS Library", page_icon="🧪", layout="wide")

if "authenticated" in st.session_state and not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.title("SEM & EDS Library")

# =========================
# Gemini Ayarları (Dinamik)
# =========================
st.sidebar.subheader("🤖 Gemini (Nitel Yorum)")
default_key = os.getenv("GEMINI_API_KEY", "")
gemini_key_input = st.sidebar.text_input(
    "Gemini API Key", value=default_key, type="password",
    help="Ortam değişkeni GEMINI_API_KEY de kullanılabilir."
)
st.sidebar.caption("LLM çıktıları nitel yorum amaçlıdır; cihaz yazılımının kantitatif analizinin yerine geçmez.")

# google-generativeai isteğe bağlı import
GENAI_AVAILABLE = True
try:
    import google.generativeai as genai
except Exception:
    GENAI_AVAILABLE = False

@st.cache_resource(show_spinner=False)
def list_gemini_models(api_key: str) -> List[str]:
    """Kullanıcının key’i ile erişebildiği ve generateContent destekleyen model adlarını döndürür."""
    if not GENAI_AVAILABLE or not api_key:
        return []
    try:
        genai.configure(api_key=api_key)
        names = []
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", []) or getattr(m, "generation_methods", [])
            # Farklı SDK sürümlerine uyumlu kontrol
            methods = [str(x).lower() for x in methods]
            if any("generatecontent" in x for x in methods) or "generateContent" in methods:
                names.append(m.name)
        # Örnek: ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'gemini-pro', ...]
        return sorted(set(names))
    except Exception:
        return []

def configure_gemini(api_key: str):
    if not GENAI_AVAILABLE:
        return False, "⚠️ `google-generativeai` kurulu değil. `pip install google-generativeai`"
    if not api_key:
        return False, "⚠️ Gemini API anahtarı yok. Sidebar’dan girin veya GEMINI_API_KEY ortam değişkenini ayarlayın."
    try:
        genai.configure(api_key=api_key)
        return True, None
    except Exception as e:
        return False, f"⚠️ Gemini yapılandırması başarısız: {e}"

def try_model_variants(name: str):
    """
    Seçilen model adı için çalışır varyasyonu bul:
    - verilen ad
    - 'models/' önekli
    - '-latest' ekli
    - hem önek hem ek
    """
    variants = []
    base = name.strip()
    if not base:
        return []
    variants.append(base)
    if not base.startswith("models/"):
        variants.append(f"models/{base}")
    if not base.endswith("-latest"):
        variants.append(f"{base}-latest")
    if not base.startswith("models/") and not base.endswith("-latest"):
        variants.append(f"models/{base}-latest")
    return list(dict.fromkeys(variants))  # benzersiz sırayı koru

def pick_working_model(api_key: str, preferred: Optional[str], discovered: List[str]):
    """
    1) Kullanıcı seçimi varsa onun varyantlarını sırayla dene
    2) Olmazsa discovered listesindeki modelleri sırayla dene
    """
    ok, err = configure_gemini(api_key)
    if not ok:
        return None, err

    candidates: List[str] = []
    if preferred:
        candidates.extend(try_model_variants(preferred))
    # discovered isimleri de (varsa) ekle
    for m in discovered:
        candidates.extend(try_model_variants(m))
    # son çare olarak bilinen isimler
    candidates.extend([
        *try_model_variants("gemini-1.5-flash"),
        *try_model_variants("gemini-1.5-pro"),
        *try_model_variants("gemini-pro"),
    ])
    # tekrarları at
    seen = set()
    ordered = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)

    # hızlı sağlık kontrolü: kısa generate_content denemesi
    for name in ordered:
        try:
            model = genai.GenerativeModel(name)
            resp = model.generate_content("ping")
            if getattr(resp, "text", "").strip() != "":
                return model, None
        except Exception:
            continue
    return None, "⚠️ Uygun bir Gemini modeli bulunamadı. Lütfen `google-generativeai` paketini güncelleyin veya farklı bir model deneyin."

# Sidebar: dinamik model listesi
available = list_gemini_models(gemini_key_input.strip())
if available:
    selected_model = st.sidebar.selectbox("Model (erişilebilir)", available, index=0)
else:
    selected_model = st.sidebar.text_input(
        "Model adı (manuel)", value="gemini-1.5-flash",
        help="Örn: gemini-1.5-flash, gemini-1.5-pro, gemini-pro veya list_models ile dönen ad."
    )

# =========================
# Kalıcı Depo
# =========================
BASE_DIR = Path("sem_eds_uploads")
RECORDS_CSV = Path("sem_eds_records.csv")
BASE_DIR.mkdir(exist_ok=True, parents=True)

RECORD_COLUMNS = [
    "entry_id", "production_name", "project_name", "producer",
    "sample_no", "test_date", "sem_files", "eds_files", "created_at",
]

def load_records() -> pd.DataFrame:
    if RECORDS_CSV.exists():
        df = pd.read_csv(RECORDS_CSV)
        for c in RECORD_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return df[RECORD_COLUMNS]
    return pd.DataFrame(columns=RECORD_COLUMNS)

def save_records(df: pd.DataFrame):
    df.to_csv(RECORDS_CSV, index=False)

def safe_name(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s) or "entry"

records_df = load_records()

# =========================
# Prompt'lar
# =========================
SEM_PROMPT = """Aşağıdaki SEM görüntüsünü eklemeli imalat (FFF/PEEK/PEKK vb.) bağlamında
nitel olarak bilimsel rapor üslubunda yorumla. Lütfen kısa başlıklarla akıcı bir metin üret:

1) Katman Yapısı ve Morfoloji:
- Katmanların görünürlüğü, süreksizlikler, yüzey pürüzlülüğü, olası yöney/kılcal izler
- Katman kalınlıklarının farklılaşması için olası nedenler (eriyik yığılma, viskoz akış sapmaları, soğuma)

2) Bağlanma ve Boşluklar:
- Katmanlar arası boşluk/void/çekinti gözlemi (var/yok, göreli görünüm)
- Bağlanma başarımı hakkında nitel değerlendirme

3) Kusur ve Artefaktlar:
- Gözlenen olası kusurlar (delaminasyon, gözeneklilik, partikül, çekme izleri vb.) ve muhtemel kaynakları

4) Mekanik Özelliklerle İlişki:
- Gözlenen mikroyapının, çekme/çekme dayanımı vb. makro davranışla nitel ilişkisi

5) Sınırlar:
- Ölçek çubuğu/büyütme bilgisi yoksa belirsizlikleri belirt; bu yorumlar nitel, kantitatif değildir.

ÇIKTI: Tamamı akıcı bir rapor metni olsun (madde madde değil), ama içinde bu başlıkların içeriğini kapsasın.
Kantitatif değer uydurma; yalnızca görüntüden çıkarılabilecek nitel gözlemleri yaz.
"""

EDS_PROMPT = """Aşağıda EDS verisinin özeti veriliyor. Bu özet, CSV/TXT verisinden türetilmiştir.
Lütfen nitel (kantitatif olmayan) bir rapor hazırla:

- Baskın element/çizgi adayları ve göreli dağılıma dair nitel yorum
- Matris ve muhtemel faz/ara yüzey ilişkileri
- Numune hazırlama kaynaklı artefakt olasılıkları (kaplama, yükleme, yüzey eğimi, topoğrafya etkisi)
- Hata/kısıtlar: ZAF/φρz düzeltmesi yokluğu, standardizasyon eksikliği, dedeksiyon limitleri, pik çakışmaları
- SEM gözlemleriyle bağ kurulabiliyorsa kısaca ilişkilendir

ÇIKTI: Bilimsel rapor üslubunda akıcı bir metin. Kantitatif wt%/at% verisi üretme; nitel kal.
"""

# =========================
# Yardımcılar (Gemini)
# =========================
def image_to_inline_part(path: Path) -> dict:
    mime = "image/jpeg"
    s = path.suffix.lower()
    if s == ".png":
        mime = "image/png"
    elif s in [".tif", ".tiff"]:
        mime = "image/tiff"
    elif s == ".bmp":
        mime = "image/bmp"
    data_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"inline_data": {"mime_type": mime, "data": data_b64}}

def get_working_model():
    return pick_working_model(gemini_key_input.strip(), selected_model, available)

def sem_gemini_analyze(image_path: Path) -> str:
    model, err = get_working_model()
    if err:
        return err
    try:
        part = image_to_inline_part(image_path)
        resp = model.generate_content([SEM_PROMPT, part], generation_config={"temperature": 0.7, "max_output_tokens": 1024})
        text = getattr(resp, "text", "") or ""
        if not text.strip():
            return "⚠️ Modelden boş yanıt geldi."
        return "⚠️ Not: Bu yorumlar LLM tarafından üretilmiş nitel değerlendirmelerdir; cihaz yazılımının kantitatif analizinin yerine geçmez.\n\n" + text
    except Exception as e:
        return f"⚠️ Gemini isteği başarısız: {e}"

def summarize_df_for_eds(df: pd.DataFrame, max_rows: int = 200) -> str:
    lines = [f"Tablo boyutu: {len(df)} satır x {df.shape[1]} sütun",
             "Sütunlar: " + ", ".join(map(str, df.columns.tolist()[:20])) + (" ..." if df.shape[1] > 20 else "")]
    head_csv = df.head(5).to_csv(index=False)
    tail_csv = df.tail(5).to_csv(index=False)
    sample = df if len(df) <= max_rows else pd.concat([df.head(max_rows//2), df.tail(max_rows//2)], ignore_index=True)
    num_cols = sample.select_dtypes(include="number").columns.tolist()
    stats_part = ""
    if num_cols:
        stats_part = "\nBasit istatistik (kırpılmış veri):\n" + sample[num_cols].describe().to_csv()
    return "\n".join(lines) + "\n\nİlk 5 satır (CSV):\n" + head_csv + "\nSon 5 satır (CSV):\n" + tail_csv + stats_part

def eds_gemini_analyze_from_df(df: pd.DataFrame) -> str:
    model, err = get_working_model()
    if err:
        return err
    try:
        summary = summarize_df_for_eds(df)
        resp = model.generate_content([EDS_PROMPT, f"\n\n=== EDS VERİ ÖZETİ ===\n{summary}\n"],
                                      generation_config={"temperature": 0.6, "max_output_tokens": 1024})
        text = getattr(resp, "text", "") or ""
        if not text.strip():
            return "⚠️ Modelden boş yanıt geldi."
        return "⚠️ Not: Bu yorumlar LLM tarafından üretilmiş nitel değerlendirmelerdir; cihaz yazılımının kantitatif analizinin yerine geçmez.\n\n" + text
    except Exception as e:
        return f"⚠️ Gemini isteği başarısız: {e}"

# =========================
# Yeni Kayıt Formu
# =========================
st.subheader("➕ Create New SEM & EDS Entry")
with st.form("sem_eds_form", clear_on_submit=True):
    c1, c2 = st.columns([1, 1])
    with c1:
        production_name = st.text_input("Raw Material, Direction and Angle", placeholder="e.g. PEEK CF ZX 45°")
        producer = st.text_input("Tester", placeholder="e.g. Zeynep Ege Uysal")
        sample_no = st.text_input("Sample No.", placeholder="e.g. 1")
    with c2:
        project_name = st.radio("Project Name", ["CREDIT", "COMPADDITIVE"], horizontal=True)
        test_date = st.date_input("Test Date", value=datetime.now().date(), format="YYYY-MM-DD")

    st.markdown("**SEM Files Upload** (multiple)")
    sem_files = st.file_uploader("Upload SEM files (images or PDFs)",
                                 type=["png", "jpg", "jpeg", "tif", "tiff", "bmp", "pdf"],
                                 accept_multiple_files=True, key="sem_uploader", label_visibility="collapsed")
    st.markdown("**EDS Files Upload** (multiple)")
    eds_files = st.file_uploader("Upload EDS files (csv, txt, xlsx, pdf, docx)",
                                 type=["csv", "txt", "xlsx", "pdf", "docx"],
                                 accept_multiple_files=True, key="eds_uploader", label_visibility="collapsed")

    submitted = st.form_submit_button("💾 Save Entry", type="primary")

if submitted:
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
    for _, row in records_df.sort_values("created_at", ascending=False).iterrows():
        title_left = row["production_name"] or "—"
        title_right = row["project_name"] or ""
        expander = st.expander(f"{title_left} ({title_right})", expanded=False)

        with expander:
            cA, cB, cC = st.columns([1, 1, 1])
            with cA:
                st.markdown(f"**Tester:** {row['producer'] or '—'}")
                st.markdown(f"**Raw Material, Direction and Angle:** {row['production_name'] or '-'}")
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
            # SEM
            if sem_list:
                st.markdown("**SEM Files**")
                for p in sem_list:
                    cols = st.columns([3, 1, 1])
                    try:
                        if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]:
                            cols[0].image(str(p), caption=p.name, use_container_width=True)
                        else:
                            cols[0].write(p.name)
                    except Exception as e:
                        cols[0].warning(f"Preview error: {e}")
                    try:
                        with open(p, "rb") as fh:
                            cols[1].download_button("⬇️ Download", data=fh.read(), file_name=p.name, mime=None,
                                                    key=f"dl_sem_{row['entry_id']}_{p.name}")
                    except Exception as e:
                        cols[1].warning(f"Download error: {e}")

                    if cols[2].button("🤖 Yorumla", key=f"an_sem_{row['entry_id']}_{p.name}"):
                        with st.spinner("Gemini nitel yorumu hazırlanıyor..."):
                            st.info(sem_gemini_analyze(p))

            # EDS
            if eds_list:
                st.markdown("**EDS Files**")
                for p in eds_list:
                    cols = st.columns([3, 1, 1])
                    shown = False
                    df_preview: Optional[pd.DataFrame] = None
                    try:
                        if p.suffix.lower() == ".csv":
                            df_preview = pd.read_csv(p)
                            cols[0].dataframe(df_preview.head(20), use_container_width=True)
                            shown = True
                        elif p.suffix.lower() == ".txt":
                            df_preview = pd.read_csv(p, sep=None, engine="python")
                            cols[0].dataframe(df_preview.head(20), use_container_width=True)
                            shown = True
                    except Exception as e:
                        cols[0].warning(f"Preview error: {e}")
                    if not shown:
                        cols[0].write(p.name)

                    try:
                        with open(p, "rb") as fh:
                            cols[1].download_button("⬇️ Download", data=fh.read(), file_name=p.name, mime=None,
                                                    key=f"dl_eds_{row['entry_id']}_{p.name}")
                    except Exception as e:
                        cols[1].warning(f"Download error: {e}")

                    if cols[2].button("🤖 Yorumla", key=f"an_eds_{row['entry_id']}_{p.name}"):
                        with st.spinner("Gemini nitel yorumu hazırlanıyor..."):
                            if df_preview is not None and not df_preview.empty:
                                st.info(eds_gemini_analyze_from_df(df_preview))
                            else:
                                st.info(
                                    "⚠️ CSV/TXT veri önizlemesi bulunamadı. EDS nitel yorumu için lütfen CSV/TXT dosyası yükleyin.\n"
                                    "PDF/DOCX doğrudan analiz edilmez; üretici yazılımından alınmış tabloyu CSV olarak ekleyin."
                                )

            st.markdown("—")
            del_col = st.columns([1, 4])[0]
            if del_col.button("🗑️ Delete This Entry", key=f"del_{row['entry_id']}"):
                try:
                    shutil.rmtree(BASE_DIR / row["entry_id"], ignore_errors=True)
                except Exception as e:
                    st.error(f"Folder delete error: {e}")
                new_df = records_df.loc[records_df["entry_id"] != row["entry_id"]].reset_index(drop=True)
                save_records(new_df)
                st.success("Entry deleted.")
                st.rerun()
