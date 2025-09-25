# ✅ COMPADDITIVE_Literature_Reviewer.py
import streamlit as st
import os
import json
from datetime import datetime
import base64
import re
import requests
import xml.etree.ElementTree as ET

# =========================
#  AUTH & PAGE METADATA
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.set_page_config(page_title="COMPADDITIVE Literature Reviewer", layout="wide")
st.title("COMPADDITIVE Literature Reviewer")

USERNAME = st.session_state.get("username", "anonymous")

# =========================
#  PERSISTENCE (FILES)
# =========================
UPLOAD_DIR = "uploaded_literature_compadditive"
METADATA_FILE = "literature_files_compadditive.json"
SAVED_LIST_FILE = "literature_saved_compadditive.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)

def _load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def _save_json(path: str, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

uploaded_files = _load_json(METADATA_FILE, [])
saved_items = _load_json(SAVED_LIST_FILE, {"items": []})

def save_metadata():
    _save_json(METADATA_FILE, uploaded_files)

def save_saved_items():
    _save_json(SAVED_LIST_FILE, saved_items)

# =========================
#  OPTION 1 (UPLOAD FLOW)
# =========================
def file_uploader():
    st.subheader("📤 Upload a new literature file")

    uploaded_file = st.file_uploader(
        "Upload file",
        type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls", "csv", "docx", "pptx"],
        label_visibility="collapsed",
        key="lr_upload_box"
    )
    title = st.text_input("Enter a title for this file", key="lr_title")
    description = st.text_area("Enter a description for this file", key="lr_desc")

    if st.button("Upload", key="lr_upload_btn") and uploaded_file and title:
        file_bytes = uploaded_file.read()
        file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        uploaded_files.append({
            "filename": uploaded_file.name,
            "title": title,
            "description": description,
            "uploader": USERNAME,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_metadata()
        st.success("File uploaded successfully.")
        st.rerun()

def display_uploaded_files():
    st.subheader("📁 Uploaded Files")
    if not uploaded_files:
        st.info("No files uploaded yet.")
        return

    for i, file in enumerate(uploaded_files):
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 2, 3, 2, 2, 1, 1, 1])
        col1.write(f"**Original:** {file['filename']}")
        col2.write(f"**Title:** {file['title']}")
        col3.write(f"**Description:** {file['description']}")
        col4.write(f"**Uploader:** {file['uploader']}")
        col5.write(f"**Date:** {file['timestamp']}")

        # Delete
        if col6.button("❌", key=f"delete_{file['filename']}"):
            file_path = os.path.join(UPLOAD_DIR, file['filename'])
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            uploaded_files.pop(i)
            save_metadata()
            st.rerun()

        # Download
        file_path = os.path.join(UPLOAD_DIR, file['filename'])
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            href = f'<a href="data:file/octet-stream;base64,{b64}" download="{file["filename"]}">📥</a>'
            col7.markdown(href, unsafe_allow_html=True)
        else:
            col7.write("—")

        # Preview toggle
        if col8.button("👁️", key=f"preview_{file['filename']}"):
            st.session_state[f"show_preview_{file['filename']}"] = not st.session_state.get(
                f"show_preview_{file['filename']}", False
            )

        # Conditional preview
        if st.session_state.get(f"show_preview_{file['filename']}", False):
            st.markdown(f"### 👁️ Preview: {file['title']}")
            if file['filename'].lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(file_path):
                st.image(file_path, use_column_width=True)
            else:
                st.markdown(
                    """
                    <div style='text-align: center; padding: 1em; border: 2px dashed #999; border-radius: 10px; background-color: #1e1e1e; color: #ddd;'>
                        🔒 <strong>Preview not available for this file type.</strong>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            st.markdown("---")

# =========================
#  OPTION 2 (SEARCH ENGINE)
#  Providers: OpenAlex, arXiv, DOAJ
# =========================
def _safe_join_authors(authorships):
    if not authorships:
        return []
    names = []
    for a in authorships:
        nm = None
        if isinstance(a, dict):
            nm = a.get("author", {}).get("display_name") or a.get("display_name")
        elif isinstance(a, str):
            nm = a
        if nm:
            names.append(nm)
    return names

def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None

def _dedupe_results(rows):
    seen = set()
    uniq = []
    for r in rows:
        key = r.get("doi") or r.get("url") or (r.get("title","").lower() + "|" + (str(r.get("year")) if r.get("year") else ""))
        if key and key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq

# ---------- OpenAlex ----------
def _abstract_from_openalex(inv_index: dict):
    try:
        positions = []
        for word, idxs in inv_index.items():
            for p in idxs:
                positions.append((p, word))
        positions.sort(key=lambda x: x[0])
        words = [w for _, w in positions]
        text = " ".join(words)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return ""

def search_openalex(query: str, year_from: int|None, year_to: int|None, oa_only: bool, doc_type: str|None, per_page=20):
    base = "https://api.openalex.org/works"
    params = {"search": query, "per_page": per_page, "sort": "relevance_score:desc"}
    filters = []
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")
    if oa_only:
        filters.append("open_access.is_oa:true")
    if doc_type and doc_type != "any":
        filters.append(f"type:{doc_type}")
    if filters:
        params["filter"] = ",".join(filters)

    try:
        r = requests.get(base, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"OpenAlex request failed: {e}")
        return []

    results = []
    for w in data.get("results", []):
        title = w.get("display_name")
        year = w.get("publication_year")
        doi = w.get("doi")
        primary_loc = w.get("primary_location") or {}
        candidate_url = _first_nonempty(
            primary_loc.get("landing_page_url"),
            primary_loc.get("pdf_url"),
            w.get("open_access", {}).get("oa_url"),
            w.get("host_venue", {}).get("url"),
            w.get("id")
        )
        authors = _safe_join_authors(w.get("authorships", []))
        venue = (w.get("host_venue") or {}).get("display_name")
        abstract = ""
        if w.get("abstract"):
            abstract = w["abstract"]
        elif w.get("abstract_inverted_index"):
            abstract = _abstract_from_openalex(w["abstract_inverted_index"])

        results.append({
            "provider": "OpenAlex",
            "id": w.get("id"),
            "title": title or "(no title)",
            "authors": authors,
            "year": year,
            "source": venue,
            "doi": doi.replace("https://doi.org/", "") if isinstance(doi, str) else None,
            "url": candidate_url,
            "abstract": abstract
        })
    return results

# ---------- arXiv (Atom feed) ----------
def _text(node):
    return (node.text or "").strip() if node is not None else ""

def _find(node, tag, ns):
    return node.find(tag, ns)

def _findall(node, tag, ns):
    return node.findall(tag, ns)

def search_arxiv(query: str, year_from: int|None, year_to: int|None, oa_only: bool, doc_type: str|None, max_results=25):
    # arXiv query language: AND with +
    q = query.replace(" ", "+")
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "COMPADDITIVE/1.0"})
        r.raise_for_status()
        xml = r.text
    except Exception as e:
        st.warning(f"arXiv request failed: {e}")
        return []

    # Parse Atom
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"
    }
    try:
        root = ET.fromstring(xml)
    except Exception as e:
        st.warning(f"arXiv parse error: {e}")
        return []

    rows = []
    for entry in _findall(root, "atom:entry", ns):
        title = _text(_find(entry, "atom:title", ns))
        summary = _text(_find(entry, "atom:summary", ns))
        published = _text(_find(entry, "atom:published", ns))  # e.g., 2024-06-15T...
        year = None
        if published:
            try:
                year = int(published[:4])
            except:
                year = None

        # Authors
        authors = []
        for a in _findall(entry, "atom:author", ns):
            nm = _text(_find(a, "atom:name", ns))
            if nm:
                authors.append(nm)

        # Links
        url_pdf = None
        url_abs = None
        for lk in _findall(entry, "atom:link", ns):
            rel = lk.attrib.get("rel", "")
            href = lk.attrib.get("href", "")
            t = lk.attrib.get("type", "")
            if t == "application/pdf":
                url_pdf = href
            if rel == "alternate":
                url_abs = href
        final_url = url_pdf or url_abs

        # DOI (optional)
        doi = None
        doi_node = _find(entry, "arxiv:doi", ns)
        if doi_node is not None and _text(doi_node):
            doi = _text(doi_node)

        item = {
            "provider": "arXiv",
            "id": _text(_find(entry, "atom:id", ns)),
            "title": title or "(no title)",
            "authors": authors,
            "year": year,
            "source": "arXiv",
            "doi": doi,
            "url": final_url or _text(_find(entry, "atom:id", ns)),
            "abstract": summary
        }
        rows.append(item)

    # Client-side filters (arXiv feed tarih filtresi kısıtlı)
    if year_from:
        rows = [x for x in rows if x["year"] and x["year"] >= year_from]
    if year_to:
        rows = [x for x in rows if x["year"] and x["year"] <= year_to]

    # OA: arXiv zaten OA; doc_type yok sayılır.
    return rows

# ---------- DOAJ (JSON API v2) ----------
def search_doaj(query: str, year_from: int|None, year_to: int|None, oa_only: bool, doc_type: str|None, page_size=25):
    # Basit arama (q=), client-side yıl filtresi
    # API: https://doaj.org/api/v2/docs#tag/Search
    url = "https://doaj.org/api/v2/search/articles/" + requests.utils.quote(query)
    params = {"pageSize": page_size}
    try:
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "COMPADDITIVE/1.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"DOAJ request failed: {e}")
        return []

    rows = []
    for rec in data.get("results", []):
        bj = rec.get("bibjson", {}) or {}
        title = bj.get("title") or "(no title)"
        year = None
        # Yıl için history ya da year alanı olabilir
        try:
            year = int(bj.get("year")) if bj.get("year") else None
        except:
            year = None

        # Authors
        authors = []
        for a in bj.get("author", []) or []:
            nm = a.get("name") or ""
            if nm:
                authors.append(nm)

        # Links
        url_link = None
        for ln in bj.get("link", []) or []:
            if ln.get("url"):
                url_link = ln["url"]
                break

        # Source / Journal
        source = None
        if bj.get("journal", {}):
            source = bj["journal"].get("title")

        doi = None
        for idt in bj.get("identifier", []) or []:
            if idt.get("type") == "doi":
                doi = idt.get("id")

        abstract = bj.get("abstract", "")

        rows.append({
            "provider": "DOAJ",
            "id": rec.get("id"),
            "title": title,
            "authors": authors,
            "year": year,
            "source": source,
            "doi": doi,
            "url": url_link,
            "abstract": abstract
        })

    # Client-side filters (OA: DOAJ zaten OA)
    if year_from:
        rows = [x for x in rows if x["year"] and x["year"] >= year_from]
    if year_to:
        rows = [x for x in rows if x["year"] and x["year"] <= year_to]

    return rows

# ---------- Unified search ----------
def unified_search(query, year_from, year_to, oa_only, doc_type, providers):
    rows = []
    if "OpenAlex" in providers:
        rows += search_openalex(query, year_from, year_to, oa_only, doc_type)
    if "arXiv" in providers:
        rows += search_arxiv(query, year_from, year_to, oa_only, doc_type)
    if "DOAJ" in providers:
        rows += search_doaj(query, year_from, year_to, oa_only, doc_type)

    rows = _dedupe_results(rows)
    # Basit sıralama: yeni → eski, başlığı olmayan sona
    rows.sort(key=lambda r: (-(r.get("year") or 0), r.get("title") is None))
    return rows

# ---- Add to Shared List ----
def add_to_shared_list(item, rationale, tags, priority, status):
    key = item.get("doi") or item.get("url") or item.get("title","").lower()
    exists = any(
        (x.get("doi") or x.get("url") or x.get("title","").lower()) == key
        for x in saved_items["items"]
    )
    if exists:
        st.warning("This item already exists in the shared list.")
        return False

    payload = {
        "id": item.get("id"),
        "title": item.get("title"),
        "url": item.get("url"),
        "doi": item.get("doi"),
        "authors": item.get("authors"),
        "year": item.get("year"),
        "source": item.get("source"),
        "provider": item.get("provider"),
        "abstract": (item.get("abstract") or "")[:2000],
        "added_by": USERNAME,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rationale": rationale,
        "tags": [t.strip() for t in (tags or "").split(",") if t.strip()],
        "priority": priority,
        "status": status
    }
    saved_items["items"].append(payload)
    save_saved_items()
    return True

# =========================
#  UI RENDER (Option 2)
# =========================
def render_search_ui():
    st.subheader("Literature search with AI")

    with st.form("lr_search_form", clear_on_submit=False):
        query = st.text_input("Enter topic or keywords", key="lr_query",
                              placeholder="e.g., Carbon Fiber Reinforced PPS")
        c1, c2, c3, c4 = st.columns([1,1,1,1])

        with c1:
            year_from = st.number_input("From year", min_value=1900, max_value=datetime.now().year, value=2015, step=1)
        with c2:
            year_to = st.number_input("To year", min_value=1900, max_value=datetime.now().year, value=datetime.now().year, step=1)
        with c3:
            oa_only = st.checkbox("Open access only", value=False)
        with c4:
            # Tip filtreleri şimdilik yalnız OpenAlex'te etkili
            doc_type = st.selectbox("Type", ["any", "journal-article", "proceedings-article", "book-chapter", "posted-content"], index=0)

        providers = st.multiselect("Providers", ["OpenAlex", "arXiv", "DOAJ"], default=["OpenAlex", "arXiv", "DOAJ"])
        submitted = st.form_submit_button("Search")

    if not st.session_state.get("lr_results"):
        st.session_state["lr_results"] = []

    if submitted:
        if not query.strip():
            st.warning("Please enter a query.")
        else:
            with st.spinner("Searching providers…"):
                results = unified_search(query.strip(), int(year_from), int(year_to), oa_only, doc_type, providers)
                st.session_state["lr_results"] = results

    # Results
    results = st.session_state.get("lr_results", [])
    st.markdown("---")
    st.subheader(f"🔎 Results ({len(results)})")
    if not results:
        st.info("No results yet. Try a query above.")
    else:
        for idx, r in enumerate(results):
            with st.container(border=True):
                tcol1, tcol2 = st.columns([0.75, 0.25])
                with tcol1:
                    st.markdown(f"**{r.get('title') or '(no title)'}**")
                    meta_bits = []
                    if r.get("year"): meta_bits.append(str(r["year"]))
                    if r.get("source"): meta_bits.append(r["source"])
                    if r.get("provider"): meta_bits.append(r["provider"])
                    st.caption(" • ".join(meta_bits) if meta_bits else "")

                    if r.get("authors"):
                        st.write(", ".join(r["authors"])[:500])

                    if r.get("abstract"):
                        st.write(r["abstract"][:500] + ("…" if len(r["abstract"]) > 500 else ""))

                    link_line = []
                    if r.get("url"):
                        link_line.append(f"[View Source]({r['url']})")
                    if r.get("doi"):
                        link_line.append(f"DOI: {r['doi']}")
                    if link_line:
                        st.markdown(" | ".join(link_line))

                with tcol2:
                    with st.popover("➕ Add to Shared List", use_container_width=True):
                        rationale = st.text_area("Why add? (rationale)", key=f"rat_{idx}", height=80)
                        tags = st.text_input("Tags (comma-separated)", key=f"tags_{idx}", placeholder="PEEK, FFF, process")
                        priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=1, key=f"prio_{idx}")
                        status = st.selectbox("Status", ["To Read", "Reading", "Read", "Summarized"], index=0, key=f"stat_{idx}")
                        if st.button("Add", key=f"add_{idx}"):
                            ok = add_to_shared_list(r, rationale, tags, priority, status)
                            if ok:
                                st.success("Added to shared list.")
                            st.rerun()

    st.markdown("---")
    st.subheader("📚 Saved Literature List")
    if not saved_items["items"]:
        st.info("No entries in the shared list yet.")
    else:
        # küçük filtreler
        f1, f2, f3 = st.columns([1,1,1])
        with f1:
            flt_user = st.text_input("Filter by user", key="flt_user")
        with f2:
            flt_tag = st.text_input("Filter by tag", key="flt_tag")
        with f3:
            flt_status = st.selectbox("Filter by status", ["(all)", "To Read", "Reading", "Read", "Summarized"], index=0, key="flt_status")

        rows = saved_items["items"]
        if flt_user.strip():
            rows = [x for x in rows if x.get("added_by","").lower().find(flt_user.lower()) >= 0]
        if flt_tag.strip():
            rows = [x for x in rows if any(flt_tag.lower() in (t or "").lower() for t in x.get("tags",[]))]
        if flt_status != "(all)":
            rows = [x for x in rows if x.get("status") == flt_status]

        for i, it in enumerate(rows):
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.6, 0.25, 0.15])
                with c1:
                    st.markdown(f"**{it.get('title') or '(no title)'}**")
                    meta = []
                    if it.get("year"): meta.append(str(it["year"]))
                    if it.get("source"): meta.append(it["source"])
                    if it.get("provider"): meta.append(it["provider"])
                    if it.get("doi"): meta.append(f"DOI:{it['doi']}")
                    st.caption(" • ".join(meta))
                    if it.get("url"):
                        st.markdown(f"[Open Link]({it['url']})")
                    if it.get("tags"):
                        st.write("Tags: " + ", ".join(it["tags"]))
                    if it.get("rationale"):
                        st.write("Notes: " + it["rationale"])
                    st.caption(f"Added by {it.get('added_by','?')} at {it.get('added_at','?')}")

                with c2:
                    st.write(f"Priority: **{it.get('priority','-')}**")
                    st.write(f"Status: **{it.get('status','-')}**")

                with c3:
                    if st.button("🗑️ Delete", key=f"del_{i}_{it.get('doi') or it.get('url') or i}"):
                        idx_real = saved_items["items"].index(it)
                        saved_items["items"].pop(idx_real)
                        save_saved_items()
                        st.rerun()

        # Export
        exp_c1, exp_c2 = st.columns([1,1])
        with exp_c1:
            if st.button("⬇️ Export JSON"):
                b = json.dumps(saved_items, indent=2, ensure_ascii=False).encode("utf-8")
                b64 = base64.b64encode(b).decode()
                href = f'<a href="data:application/json;base64,{b64}" download="literature_saved_compadditive.json">Download JSON</a>'
                st.markdown(href, unsafe_allow_html=True)

# =========================
#  MODE SELECTOR
# =========================
st.subheader("How would you like to proceed?")
mode = st.radio(
    label="Select a mode",
    options=["Uploading existing literature files", "Literature search with AI"],
    index=0
)

if mode == "Uploading existing literature files":
    file_uploader()
    display_uploaded_files()
else:
    render_search_ui()
