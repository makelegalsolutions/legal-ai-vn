import os
import re
import json
import unicodedata
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path

# ========================================
# CONFIG
# ========================================
VECTORSTORE_DIR = "data/vectorstore"

# Files will be versioned
CHUNKS_METADATA_FILE = None  # Will be set dynamically
FAISS_INDEX_FILE = None       # Will be set dynamically
INDEX_METADATA_FILE = None    # Will be set dynamically

# Thresholds
STRICT_DOMAIN_THRESHOLD = 0.60
STRICT_TOP1_THRESHOLD = 0.82
RETRIEVAL_THRESHOLD = 0.45
MAX_RETURN_TEXT_CHARS = 500

# Global state for hot-swap
_current_version = None
_chunks = []
_index = None
_embedding_model = None
_chunk_by_id = {}

# ========================================
# ENSURE FAISS AVAILABLE (TỪ LOCAL HOẶC DRIVE)
# ========================================
def ensure_faiss_available():
    """Đảm bảo có FAISS index local, tải từ Drive nếu cần"""
    local_index = os.path.join(VECTORSTORE_DIR, "legal_index.faiss")
    
    if os.path.exists(local_index) and os.path.getsize(local_index) > 0:
        print("✅ FAISS found locally")
        return True
    
    # Thử tải từ Drive
    try:
        from .faiss_drive_manager import load_faiss_version_from_drive, FAISS_DRIVE_FOLDER_ID
        
        # Lấy FAISS_DRIVE_FOLDER_ID từ environment variable
        drive_folder_id = os.environ.get("FAISS_DRIVE_FOLDER_ID")
        
        if drive_folder_id:
            print("📥 FAISS not found locally, downloading from Drive...")
            if load_faiss_version_from_drive(drive_folder_id):
                print("✅ FAISS downloaded from Drive successfully")
                return True
            else:
                print("⚠️ Failed to download FAISS from Drive")
        else:
            print("⚠️ FAISS_DRIVE_FOLDER_ID not set, cannot load from Drive")
    except ImportError:
        print("⚠️ faiss_drive_manager not found, using local FAISS only")
    except Exception as e:
        print(f"⚠️ Failed to load from Drive: {e}")
    
    return False

# ========================================
# GET LATEST VERSION
# ========================================
def get_latest_version():
    version_file = os.path.join(VECTORSTORE_DIR, "latest_version.txt")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            return f.read().strip()
    return None

def get_versioned_paths(version):
    """Get versioned file paths"""
    return {
        "faiss": os.path.join(VECTORSTORE_DIR, f"legal_index_{version}.faiss"),
        "metadata": os.path.join(VECTORSTORE_DIR, f"index_metadata_{version}.json"),
        "chunks": os.path.join(VECTORSTORE_DIR, f"chunks_metadata_{version}.json")
    }

# ========================================
# LOAD VECTORSTORE WITH VERSIONING
# ========================================
def load_version(version=None):
    global _current_version, _chunks, _index, _embedding_model, _chunk_by_id
    global FAISS_INDEX_FILE, CHUNKS_METADATA_FILE, INDEX_METADATA_FILE
    
    # Đảm bảo có FAISS local trước khi load
    ensure_faiss_available()
    
    if version is None:
        version = get_latest_version()
    
    if not version:
        print("⚠️ No version found. Vectorstore not initialized.")
        return False
    
    # Check if already loaded
    if _current_version == version and _index is not None:
        return True
    
    paths = get_versioned_paths(version)
    
    if not all(os.path.exists(p) for p in paths.values()):
        print(f"❌ Version {version} missing files")
        return False
    
    try:
        # Load chunks metadata
        with open(paths["chunks"], "r", encoding="utf-8") as f:
            _chunks = json.load(f)
        
        # Load FAISS index
        _index = faiss.read_index(paths["faiss"])
        
        # Load index metadata
        with open(paths["metadata"], "r", encoding="utf-8") as f:
            index_meta = json.load(f)
        
        MODEL_NAME = index_meta["model_name"]
        _embedding_model = SentenceTransformer(MODEL_NAME)
        
        # Create fast lookup map
        _chunk_by_id = {i: chunk for i, chunk in enumerate(_chunks)}
        
        # Update current version
        _current_version = version
        
        # Set global file paths for compatibility
        FAISS_INDEX_FILE = paths["faiss"]
        CHUNKS_METADATA_FILE = paths["chunks"]
        INDEX_METADATA_FILE = paths["metadata"]
        
        print(f"✅ Loaded version {version} | {len(_chunks)} chunks | {_index.ntotal} vectors")
        return True
        
    except Exception as e:
        print(f"❌ Error loading version {version}: {e}")
        return False

def check_and_reload():
    """Check for new version and reload if needed"""
    latest = get_latest_version()
    if latest and latest != _current_version:
        print(f"🔄 Detected new version: {latest} (current: {_current_version})")
        return load_version(latest)
    return True

# ========================================
# INITIAL LOAD
# ========================================
print("📥 Initializing search pipeline with versioning...")
load_version()

# ========================================
# NORMALIZE TEXT
# ========================================
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text

# ========================================
# OOS KEYWORDS
# ========================================
OOS_KEYWORDS = [
    "thai sản", "bảo hiểm xã hội", "hợp đồng lao động", "nghỉ việc",
    "mũ bảo hiểm", "vượt đèn đỏ", "bằng lái", "công chứng",
    "di chúc", "thừa kế", "lừa đảo", "đánh nhau", "ly hôn"
]

def detect_out_of_scope(query: str, query_emb=None, top1_score: float = 0.0):
    q_norm = normalize_text(query)
    for kw in OOS_KEYWORDS:
        if kw in q_norm:
            return True, f"Câu hỏi thuộc lĩnh vực chưa được hỗ trợ ({kw})."
    
    if top1_score < STRICT_TOP1_THRESHOLD and top1_score > 0:
        return True, f"Không tìm thấy căn cứ pháp lý đủ tin cậy (score={top1_score:.3f})."
    
    return False, ""

# ========================================
# MAIN LEGAL SEARCH FUNCTION
# ========================================
def legal_search(
    query: str,
    top_k: int = 8,
    threshold: float = RETRIEVAL_THRESHOLD,
    return_full_text: bool = False
):
    """
    Tìm kiếm văn bản pháp luật tốt nhất cho câu hỏi.
    Supports hot-swap versioning and auto-download from Drive.
    """
    # Check for new version on each search
    check_and_reload()
    
    if not _chunks or _index is None or _embedding_model is None:
        return {
            "status": "no_vectorstore",
            "message": "Hệ thống chưa được khởi tạo dữ liệu pháp luật. Vui lòng chạy pipeline trước.",
            "results": [],
            "top1_score": 0.0
        }

    # Embedding query
    query_emb = _embedding_model.encode(
        f"query: {query}",
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype(np.float32).reshape(1, -1)

    # FAISS Search
    scores, indices = _index.search(query_emb, top_k)
    top1_score = float(scores[0][0]) if len(scores[0]) > 0 else 0.0

    # OOS Detection
    is_oos, oos_message = detect_out_of_scope(query, query_emb, top1_score)

    if is_oos:
        return {
            "status": "out_of_scope",
            "message": oos_message,
            "results": [],
            "top1_score": round(top1_score, 4)
        }

    # Build results
    results = []
    for score, idx in zip(scores[0], indices[0]):
        score = float(score)
        if idx == -1 or score < threshold:
            continue

        chunk = _chunk_by_id.get(int(idx))
        if not chunk:
            continue

        full_text = chunk.get("text", "")

        results.append({
            "rank": len(results) + 1,
            "score": round(score, 4),
            "chunk_id": chunk.get("chunk_id"),
            "doc_id": chunk.get("doc_id"),
            "article": chunk.get("article", ""),
            "title": chunk.get("title", ""),
            "file_name": chunk.get("file_name", ""),
            "text": full_text if return_full_text else (
                full_text[:MAX_RETURN_TEXT_CHARS] + "..." 
                if len(full_text) > MAX_RETURN_TEXT_CHARS 
                else full_text
            )
        })

    if not results:
        return {
            "status": "no_result",
            "message": "Không tìm thấy văn bản pháp luật phù hợp với câu hỏi.",
            "results": [],
            "top1_score": round(top1_score, 4)
        }

    return {
        "status": "ok",
        "message": f"Tìm thấy {len(results)} kết quả liên quan.",
        "results": results,
        "top1_score": round(top1_score, 4)
    }


# ========================================
# EXPORT FUNCTION FOR STATUS CHECK
# ========================================
def get_search_status():
    """Trả về trạng thái hiện tại của search pipeline"""
    return {
        "has_chunks": len(_chunks) > 0 if _chunks else False,
        "has_index": _index is not None,
        "has_model": _embedding_model is not None,
        "current_version": _current_version,
        "total_chunks": len(_chunks) if _chunks else 0,
        "vectorstore_dir": VECTORSTORE_DIR
    }


# ========================================
# TEST FUNCTION
# ========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTING LEGAL SEARCH (with versioning + Drive support)")
    print("="*60)
    
    # Kiểm tra trạng thái
    status = get_search_status()
    print(f"\n📊 Search Pipeline Status:")
    print(f"   Chunks loaded: {status['has_chunks']}")
    print(f"   FAISS index: {status['has_index']}")
    print(f"   Model loaded: {status['has_model']}")
    print(f"   Current version: {status['current_version']}")
    print(f"   Total chunks: {status['total_chunks']}")
    
    test_queries = [
        "Điều kiện để được nghỉ thai sản là gì?",
        "Mức phạt vượt đèn đỏ hiện nay bao nhiêu?",
        "Thời hạn khiếu nại quyết định hành chính là bao lâu?"
    ]
    
    for q in test_queries:
        print(f"\n🔍 Query: {q}")
        result = legal_search(q, top_k=5, return_full_text=False)
        
        print(f"Status: {result['status']}")
        if result['status'] == "ok":
            for r in result['results'][:3]:
                print(f"   {r['rank']}. [{r['score']}] {r['article']} - {r['title'][:80]}...")
        else:
            print(f"   Message: {result['message']}")
    
    print("\n✅ Search pipeline ready to use!")
