import os
import re
import json
import unicodedata
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path
from typing import List, Dict, Tuple, Any

# ========================================
# BM25 IMPORTS
# ========================================
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    print("⚠️ rank_bm25 not installed. Run: pip install rank-bm25")

# ========================================
# CONFIG
# ========================================
VECTORSTORE_DIR = "data/vectorstore"
CHUNKS_FILE = "data/chunks/legal_chunks_latest.json"

# Files will be versioned
CHUNKS_METADATA_FILE = None  # Will be set dynamically
FAISS_INDEX_FILE = None       # Will be set dynamically
INDEX_METADATA_FILE = None    # Will be set dynamically

# Thresholds
STRICT_DOMAIN_THRESHOLD = 0.60
STRICT_TOP1_THRESHOLD = 0.82
RETRIEVAL_THRESHOLD = 0.45
MAX_RETURN_TEXT_CHARS = 500

# Hybrid search weights
VECTOR_WEIGHT = 0.6  # Trọng số cho vector search (FAISS)
BM25_WEIGHT = 0.4    # Trọng số cho BM25 (keyword)
RRF_K = 60           # Hằng số cho Reciprocal Rank Fusion

# Global state for hot-swap
_current_version = None
_chunks = []
_index = None
_embedding_model = None
_chunk_by_id = {}

# BM25 state
_bm25_index = None
_bm25_chunks_text = []
_bm25_chunks_id = []

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
        from .faiss_drive_manager import load_faiss_version_from_drive
        
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
# BUILD BM25 INDEX
# ========================================
def build_bm25_index():
    """Xây dựng BM25 index từ chunks hiện có (chỉ chạy 1 lần)"""
    global _bm25_index, _bm25_chunks_text, _bm25_chunks_id
    
    if not BM25_AVAILABLE:
        print("⚠️ BM25 not available, skipping index build")
        return False
    
    if _bm25_index is not None:
        print("✅ BM25 index already exists")
        return True
    
    # Load chunks từ file nếu chưa có trong memory
    chunks_data = _chunks
    if not chunks_data and os.path.exists(CHUNKS_FILE):
        try:
            with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
                chunks_data = json.load(f)
            print(f"📥 Loaded {len(chunks_data)} chunks from file for BM25")
        except Exception as e:
            print(f"❌ Failed to load chunks for BM25: {e}")
            return False
    
    if not chunks_data:
        print("⚠️ No chunks available for BM25 index")
        return False
    
    # Tokenize và chuẩn bị text cho BM25
    _bm25_chunks_text = []
    _bm25_chunks_id = []
    
    for chunk in chunks_data:
        # Kết hợp các trường để tìm kiếm
        text = chunk.get("text", "")
        article = chunk.get("article", "")
        title = chunk.get("title", "")
        
        # Tạo text cho BM25 (ưu tiên các trường quan trọng)
        bm25_text = f"{article} {title} {text}"
        bm25_text = normalize_text(bm25_text)
        
        if bm25_text.strip():
            _bm25_chunks_text.append(bm25_text.split())
            _bm25_chunks_id.append(chunk.get("chunk_id", ""))
    
    # Xây dựng BM25 index
    if _bm25_chunks_text:
        _bm25_index = BM25Okapi(_bm25_chunks_text)
        print(f"✅ BM25 index built with {len(_bm25_chunks_text)} chunks")
        return True
    else:
        print("❌ Failed to build BM25 index")
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
        
        # Build BM25 index từ chunks đã load
        build_bm25_index()
        
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
# VECTOR SEARCH (FAISS)
# ========================================
def vector_search(query: str, top_k: int = 20) -> List[Dict]:
    """Tìm kiếm bằng FAISS (dense vector)"""
    if _index is None or _embedding_model is None:
        return []
    
    # Embedding query
    query_emb = _embedding_model.encode(
        f"query: {query}",
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype(np.float32).reshape(1, -1)
    
    # FAISS Search
    scores, indices = _index.search(query_emb, top_k)
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        score = float(score)
        if idx == -1 or score < RETRIEVAL_THRESHOLD:
            continue
        
        chunk = _chunk_by_id.get(int(idx))
        if chunk:
            results.append({
                "chunk_id": chunk.get("chunk_id", ""),
                "score": score,
                "rank": len(results) + 1,
                "chunk": chunk
            })
    
    return results


# ========================================
# BM25 SEARCH
# ========================================
def bm25_search(query: str, top_k: int = 20) -> List[Dict]:
    """Tìm kiếm bằng BM25 (keyword search)"""
    if _bm25_index is None or not _bm25_chunks_text:
        return []
    
    tokenized_query = normalize_text(query).split()
    scores = _bm25_index.get_scores(tokenized_query)
    
    # Lấy top_k kết quả
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        if idx < len(_bm25_chunks_id):
            chunk_id = _bm25_chunks_id[idx]
            score = float(scores[idx])
            
            # Tìm chunk đầy đủ
            chunk_data = _chunk_by_id.get(chunk_id, {})
            
            results.append({
                "chunk_id": chunk_id,
                "score": score,
                "rank": len(results) + 1,
                "chunk": chunk_data
            })
    
    return results


# ========================================
# RECIPROCAL RANK FUSION (RRF)
# ========================================
def reciprocal_rank_fusion(
    vector_results: List[Dict], 
    bm25_results: List[Dict], 
    k: int = RRF_K
) -> List[Dict]:
    """
    Gộp kết quả từ vector search và BM25 bằng RRF
    Công thức: score = 1/(k + rank)
    """
    fusion_scores = {}
    
    # Vector search results
    for item in vector_results:
        chunk_id = item["chunk_id"]
        rank = item["rank"]
        fusion_scores[chunk_id] = fusion_scores.get(chunk_id, 0) + (1 / (k + rank))
    
    # BM25 results
    for item in bm25_results:
        chunk_id = item["chunk_id"]
        rank = item["rank"]
        fusion_scores[chunk_id] = fusion_scores.get(chunk_id, 0) + (1 / (k + rank))
    
    # Sắp xếp và chuyển thành list
    sorted_items = sorted(fusion_scores.items(), key=lambda x: x[1], reverse=True)
    
    results = []
    for idx, (chunk_id, score) in enumerate(sorted_items):
        chunk_data = _chunk_by_id.get(chunk_id, {})
        if chunk_data:
            results.append({
                "rank": idx + 1,
                "score": round(score, 6),
                "chunk_id": chunk_id,
                "doc_id": chunk_data.get("doc_id", ""),
                "article": chunk_data.get("article", ""),
                "title": chunk_data.get("title", ""),
                "file_name": chunk_data.get("file_name", ""),
                "text": chunk_data.get("text", "")
            })
    
    return results


# ========================================
# MAIN LEGAL SEARCH FUNCTION (HYBRID)
# ========================================
def legal_search(
    query: str,
    top_k: int = 8,
    threshold: float = RETRIEVAL_THRESHOLD,
    return_full_text: bool = False,
    use_hybrid: bool = True
):
    """
    Tìm kiếm văn bản pháp luật với Hybrid Search (BM25 + FAISS)
    
    Args:
        query: Câu hỏi của người dùng
        top_k: Số kết quả trả về
        threshold: Ngưỡng độ tin cậy
        return_full_text: Trả về toàn bộ text hay chỉ trích yếu
        use_hybrid: Sử dụng hybrid search (True) hoặc chỉ vector search (False)
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
    
    # Vector search (luôn chạy để lấy top1_score cho OOS detection)
    vector_results = vector_search(query, top_k=top_k * 2)
    
    if not vector_results:
        return {
            "status": "no_result",
            "message": "Không tìm thấy văn bản pháp luật phù hợp với câu hỏi.",
            "results": [],
            "top1_score": 0.0
        }
    
    top1_score = vector_results[0]["score"] if vector_results else 0.0
    
    # OOS Detection
    is_oos, oos_message = detect_out_of_scope(query, None, top1_score)
    
    if is_oos:
        return {
            "status": "out_of_scope",
            "message": oos_message,
            "results": [],
            "top1_score": round(top1_score, 4)
        }
    
    # Hybrid search hoặc chỉ vector search
    if use_hybrid and BM25_AVAILABLE and _bm25_index is not None:
        # BM25 search
        bm25_results = bm25_search(query, top_k=top_k * 2)
        
        # RRF Fusion
        results = reciprocal_rank_fusion(vector_results, bm25_results)
        
        # Lọc theo threshold (tùy chọn)
        # results = [r for r in results if r["score"] >= threshold]
        results = results[:top_k]
        
        search_type = "hybrid (FAISS + BM25)"
    else:
        # Chỉ vector search
        results = []
        for item in vector_results[:top_k]:
            chunk = item["chunk"]
            results.append({
                "rank": len(results) + 1,
                "score": round(item["score"], 4),
                "chunk_id": chunk.get("chunk_id", ""),
                "doc_id": chunk.get("doc_id", ""),
                "article": chunk.get("article", ""),
                "title": chunk.get("title", ""),
                "file_name": chunk.get("file_name", ""),
                "text": chunk.get("text", "")[:MAX_RETURN_TEXT_CHARS] + "..." if not return_full_text else chunk.get("text", "")
            })
        search_type = "vector (FAISS only)"
    
    if not results:
        return {
            "status": "no_result",
            "message": "Không tìm thấy văn bản pháp luật phù hợp với câu hỏi.",
            "results": [],
            "top1_score": round(top1_score, 4)
        }
    
    return {
        "status": "ok",
        "message": f"Tìm thấy {len(results)} kết quả liên quan (search type: {search_type})",
        "results": results,
        "top1_score": round(top1_score, 4),
        "search_type": search_type
    }


# ========================================
# EXPORT FUNCTIONS
# ========================================
def get_search_status():
    """Trả về trạng thái hiện tại của search pipeline"""
    return {
        "has_chunks": len(_chunks) > 0 if _chunks else False,
        "has_index": _index is not None,
        "has_model": _embedding_model is not None,
        "has_bm25": _bm25_index is not None,
        "current_version": _current_version,
        "total_chunks": len(_chunks) if _chunks else 0,
        "vectorstore_dir": VECTORSTORE_DIR
    }


def force_rebuild_bm25():
    """Force rebuild BM25 index (gọi khi chunks thay đổi)"""
    global _bm25_index, _bm25_chunks_text, _bm25_chunks_id
    _bm25_index = None
    _bm25_chunks_text = []
    _bm25_chunks_id = []
    return build_bm25_index()


# ========================================
# INITIAL LOAD
# ========================================
print("📥 Initializing search pipeline with Hybrid Search (FAISS + BM25)...")
load_version()


# ========================================
# TEST FUNCTION
# ========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTING HYBRID SEARCH (FAISS + BM25)")
    print("="*60)
    
    # Kiểm tra trạng thái
    status = get_search_status()
    print(f"\n📊 Search Pipeline Status:")
    print(f"   Chunks loaded: {status['has_chunks']}")
    print(f"   FAISS index: {status['has_index']}")
    print(f"   BM25 index: {status['has_bm25']}")
    print(f"   Model loaded: {status['has_model']}")
    print(f"   Current version: {status['current_version']}")
    print(f"   Total chunks: {status['total_chunks']}")
    
    test_queries = [
        "Điều kiện để được nghỉ thai sản là gì?",
        "Mức phạt vượt đèn đỏ hiện nay bao nhiêu?",
        "Thành lập công ty TNHH cần những gì?"
    ]
    
    for q in test_queries:
        print(f"\n🔍 Query: {q}")
        
        # Hybrid search
        result = legal_search(q, top_k=5, use_hybrid=True)
        print(f"   Hybrid search - Status: {result['status']} | Type: {result.get('search_type', 'N/A')}")
        if result['status'] == "ok":
            for r in result['results'][:3]:
                print(f"      {r['rank']}. [{r['score']}] {r['article']} - {r['title'][:60]}...")
        
        # Vector only (để so sánh)
        result_vector = legal_search(q, top_k=5, use_hybrid=False)
        print(f"   Vector only - Status: {result_vector['status']}")
    
    print("\n✅ Hybrid Search pipeline ready to use!")
