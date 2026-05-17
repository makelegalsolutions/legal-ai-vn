import os
import re
import json
from pathlib import Path
from datetime import datetime

# ========================================
# CONFIG
# ========================================
TEXTS_DIR = "data/texts"
CHUNKS_DIR = "data/chunks"
TEXTS_LATEST = os.path.join(TEXTS_DIR, "legal_texts_latest.json")

os.makedirs(CHUNKS_DIR, exist_ok=True)

CHUNK_SIZE_LIMIT = 2500  # cảnh báo chunk quá dài

# ========================================
# LOAD CLEANED TEXTS FROM PREVIOUS STEP
# ========================================
if not os.path.exists(TEXTS_LATEST):
    print("❌ Không tìm thấy file: legal_texts_latest.json")
    print("Vui lòng chạy text_processing.py trước!")
    exit(1)

with open(TEXTS_LATEST, "r", encoding="utf-8") as f:
    TEXTS = json.load(f)

print(f"📥 Đã load {len(TEXTS)} văn bản để chunking.")

# ========================================
# RESET
# ========================================
CHUNKS = []
DOC_RELATIONS = {}

# ========================================
# REGEX PATTERNS
# ========================================

DIEU_SPLIT_PATTERN = re.compile(
    r'((?:^|\n)(?:Điều|Ðiều|DIEU)\s+\d+[A-Za-z0-9\-\._\/]*)',
    re.IGNORECASE | re.MULTILINE
)

ARTICLE_EXTRACT_PATTERN = re.compile(
    r"^(?:Điều|Ðiều|DIEU)\s+\d+[A-Za-z0-9\-\._\/]*",
    re.IGNORECASE | re.MULTILINE
)

TITLE_PATTERN = re.compile(
    r"(?:Điều|Ðiều|DIEU)\s+\d+[A-Za-z0-9\-\._\/]*[\.\:\-]\s*(.+?)(?=\n(?:Điều|Ðiều|DIEU|Chương|\Z))",
    re.IGNORECASE | re.DOTALL
)

KHOAN_PATTERN = re.compile(
    r"Khoản\s+\d+[A-Za-z0-9\-]*",
    re.IGNORECASE
)

DIEM_PATTERN = re.compile(
    r"Điểm\s+[a-zđ]",
    re.IGNORECASE
)

CITATION_PATTERN = re.compile(
    r"(?:Điều|Khoản|Điểm)\s+[A-Za-z0-9\-]+",
    re.IGNORECASE
)

FULL_CITATION_PATTERN = re.compile(
    r"(?:Điểm\s+[a-zđ]\s+)?(?:Khoản\s+\d+\s+)?(?:Điều|Ðiều)\s+\d+[A-Za-z0-9\-]*",
    re.IGNORECASE
)

# LEGAL RELATION PATTERNS
SO_HIEU_PATTERN = r"([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ][A-ZĐÂĂÔƠƯ0-9\-]{1,25})"

_AMENDS_VERB = r"(?:sửa đổi|bổ sung)(?:,\s*bổ sung)?"
_AMENDS_PREP = r"(?:\s+(?:và\s+)?(?:bởi|tại|theo|một số điều của|một số điều theo|một số điều bởi))?"
_DOC_TYPE = r"(?:Thông tư|Nghị định|Luật|Quyết định|Pháp lệnh|Nghị quyết)"

AMENDS_PATTERN = re.compile(
    _AMENDS_VERB + _AMENDS_PREP + r"\s+" + _DOC_TYPE + r"\s+số\s+" + SO_HIEU_PATTERN,
    re.IGNORECASE
)

REPEALS_PATTERN = re.compile(
    r"(?:bãi bỏ|hết hiệu lực)\s+" + _DOC_TYPE + r"\s+số\s+" + SO_HIEU_PATTERN,
    re.IGNORECASE
)

REPLACE_PATTERN = re.compile(
    r"thay thế\s+" + _DOC_TYPE + r"\s+số\s+" + SO_HIEU_PATTERN,
    re.IGNORECASE
)

EFFECTIVE_PATTERN = re.compile(
    r"có hiệu lực(?:\s+thi\s+hành)?(?:\s+kể\s+từ)?\s+(?:từ\s+)?ngày\s+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})",
    re.IGNORECASE
)

VBHN_FULL_PATTERN = re.compile(
    r"^(.+)-(\d+)-VBHN-([A-Z0-9\-]+)-(\d{4})$",
    re.IGNORECASE
)

# ========================================
# HELPER FUNCTIONS
# ========================================

def normalize_text(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"([A-ZĐÂĂÔƠƯ])\s+-\s*([A-ZĐÂĂÔƠƯ0-9])", r"\1-\2", text)
    text = re.sub(r"([A-ZĐÂĂÔƠƯ])\s*-\s+([A-ZĐÂĂÔƠƯ0-9])", r"\1-\2", text)

    replacements = [
        (r"Lu\s+ật", "Luật"),
        (r"Ngh\s+ị\s+định", "Nghị định"),
        (r"Ngh\s+ị\s+quyết", "Nghị quyết"),
        (r"Th\s+ông\s+tư", "Thông tư"),
        (r"Quy\s+ết\s+định", "Quyết định"),
        (r"Pháp\s+lệnh", "Pháp lệnh"),
        (r"N\s*[Đđ]\s*-\s*CP", "NĐ-CP"),
        (r"s\s+ố", "số"),
        (r"đư\s+ợc", "được"),
        (r"b\s+ởi", "bởi"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def normalize_doc_ref(ref: str) -> str:
    if not ref:
        return ""
    ref = ref.upper().strip()
    ref = ref.replace("/", "-")
    ref = re.sub(r"\s+", "-", ref)
    ref = re.sub(r"-+", "-", ref)
    return ref


def extract_file_metadata(file_name: str) -> dict:
    base_name = os.path.splitext(file_name)[0]
    base_name = normalize_doc_ref(base_name)

    doc_id = base_name
    version_id = ""
    is_vbhn = False
    vbhn_so = ""
    vbhn_coquan = ""
    vbhn_nam = ""

    match = VBHN_FULL_PATTERN.match(base_name)
    if match:
        doc_id = normalize_doc_ref(match.group(1))
        vbhn_so = match.group(2)
        vbhn_coquan = match.group(3)
        vbhn_nam = match.group(4)
        version_id = f"{vbhn_so}-VBHN-{vbhn_coquan}-{vbhn_nam}"
        is_vbhn = True

    return {
        "doc_id": doc_id,
        "version_id": version_id,
        "is_vbhn": is_vbhn,
        "vbhn_so": vbhn_so,
        "vbhn_coquan": vbhn_coquan,
        "vbhn_nam": vbhn_nam
    }


def extract_legal_events(text: str) -> dict:
    text = normalize_text(text)
    amends = [normalize_doc_ref(x) for x in AMENDS_PATTERN.findall(text)]
    repeals = [normalize_doc_ref(x) for x in REPEALS_PATTERN.findall(text)]
    replaces = [normalize_doc_ref(x) for x in REPLACE_PATTERN.findall(text)]

    effective_date = ""
    match = EFFECTIVE_PATTERN.search(text)
    if match:
        effective_date = match.group(1)

    return {
        "amends": list(dict.fromkeys(amends)),
        "repeals": list(dict.fromkeys(repeals)),
        "replaces": list(dict.fromkeys(replaces)),
        "effective_date": effective_date
    }


def split_by_dieu(text: str) -> list:
    if not text or not text.strip():
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = DIEU_SPLIT_PATTERN.split(text)
    results = []
    current_chunk = ""

    for part in parts:
        if DIEU_SPLIT_PATTERN.match(part):
            if current_chunk.strip():
                results.append(current_chunk.strip())
            current_chunk = part
        else:
            current_chunk += part

    if current_chunk.strip():
        results.append(current_chunk.strip())

    return [r.strip() for r in results if len(r.strip()) > 100]


# ========================================
# MAIN PROCESSING
# ========================================

print("🚀 Bắt đầu chunking văn bản pháp luật...")

for item in TEXTS:
    source = item.get("source", "")
    text = item.get("text", "")

    if not source or not text.strip():
        continue

    file_name = os.path.basename(source)
    file_meta = extract_file_metadata(file_name)

    text = normalize_text(text)
    legal_events = extract_legal_events(text)

    # Document-level relations
    DOC_RELATIONS[file_meta["doc_id"]] = {
        "doc_id": file_meta["doc_id"],
        "is_vbhn": file_meta["is_vbhn"],
        "version_id": file_meta["version_id"],
        "file_name": file_name,
        "amends": legal_events["amends"],
        "repeals": legal_events["repeals"],
        "replaces": legal_events["replaces"],
        "effective_date": legal_events["effective_date"],
    }

    # Chunking by Điều
    dieu_chunks = split_by_dieu(text)
    if not dieu_chunks:
        dieu_chunks = [text]

    for idx, chunk_text in enumerate(dieu_chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue

        article_match = ARTICLE_EXTRACT_PATTERN.search(chunk_text)
        article = article_match.group(0).strip() if article_match else ""

        title = ""
        title_match = TITLE_PATTERN.search(chunk_text)
        if title_match:
            title = title_match.group(1).strip()
            title = title.split("\n")[0].strip()
            if len(title) > 250:
                title = title[:250].rsplit(' ', 1)[0] + "..."

        khoans = list(dict.fromkeys(KHOAN_PATTERN.findall(chunk_text)))
        diems = list(dict.fromkeys(DIEM_PATTERN.findall(chunk_text)))

        citations = list(dict.fromkeys(c.strip() for c in CITATION_PATTERN.findall(chunk_text)))
        full_citations = list(dict.fromkeys(c.strip() for c in FULL_CITATION_PATTERN.findall(chunk_text)))

        chunk_type = "article" if article else "fallback"
        article_id = normalize_doc_ref(article) if article else f"chunk-{idx}"
        
        chunk_id = f"{file_meta['doc_id']}::{article_id}"
        if file_meta["version_id"]:
            chunk_id = f"{chunk_id}::{file_meta['version_id']}"

        CHUNKS.append({
            "chunk_id": chunk_id,
            "doc_id": file_meta["doc_id"],
            "version_id": file_meta["version_id"],
            "is_vbhn": file_meta["is_vbhn"],
            "vbhn_so": file_meta["vbhn_so"],
            "vbhn_coquan": file_meta["vbhn_coquan"],
            "vbhn_nam": file_meta["vbhn_nam"],
            "source": source,
            "file_name": file_name,
            "article": article,
            "title": title,
            "khoans": khoans,
            "diems": diems,
            "citations": citations,
            "full_citations": full_citations,
            "effective_date": legal_events["effective_date"],
            "chunk_type": chunk_type,
            "char_length": len(chunk_text),
            "text": chunk_text
        })

# ========================================
# SAVE RESULTS
# ========================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Save Chunks
chunks_file = os.path.join(CHUNKS_DIR, f"legal_chunks_{timestamp}.json")
with open(chunks_file, "w", encoding="utf-8") as f:
    json.dump(CHUNKS, f, ensure_ascii=False, indent=2)

with open(os.path.join(CHUNKS_DIR, "legal_chunks_latest.json"), "w", encoding="utf-8") as f:
    json.dump(CHUNKS, f, ensure_ascii=False, indent=2)

# Save Document Relations
relations_file = os.path.join(CHUNKS_DIR, f"doc_relations_{timestamp}.json")
with open(relations_file, "w", encoding="utf-8") as f:
    json.dump(DOC_RELATIONS, f, ensure_ascii=False, indent=2)

with open(os.path.join(CHUNKS_DIR, "doc_relations_latest.json"), "w", encoding="utf-8") as f:
    json.dump(DOC_RELATIONS, f, ensure_ascii=False, indent=2)

# ========================================
# FINAL REPORT
# ========================================

print("=" * 70)
print("✅ CHUNKING PIPELINE HOÀN THÀNH")
print(f"Tổng chunks     : {len(CHUNKS)}")
print(f"Tổng documents  : {len(DOC_RELATIONS)}")

long_chunks = [c for c in CHUNKS if c["char_length"] > CHUNK_SIZE_LIMIT]
if long_chunks:
    print(f"⚠️  Có {len(long_chunks)} chunk dài > {CHUNK_SIZE_LIMIT} ký tự")

vbhn_count = sum(1 for c in CHUNKS if c["is_vbhn"])
article_count = sum(1 for c in CHUNKS if c["chunk_type"] == "article")
print(f"VBHN chunks     : {vbhn_count}")
print(f"Article chunks  : {article_count}")

print(f"\n📁 Chunks latest   → data/chunks/legal_chunks_latest.json")
print(f"📁 Relations latest → data/chunks/doc_relations_latest.json")
print("=" * 70)
