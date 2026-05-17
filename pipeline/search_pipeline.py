import os
import re
import json
import unicodedata
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# ========================================
# CONFIG
# ========================================
VECTORSTORE_DIR = "data/vectorstore"

CHUNKS_METADATA_FILE = os.path.join(VECTORSTORE_DIR, "chunks_metadata.json")
FAISS_INDEX_FILE = os.path.join(VECTORSTORE_DIR, "legal_index.faiss")
INDEX_METADATA_FILE = os.path.join(VECTORSTORE_DIR, "index_metadata.json")

# Thresholds
STRICT_DOMAIN_THRESHOLD = 0.60
STRICT_TOP1_THRESHOLD = 0.82
RETRIEVAL_THRESHOLD = 0.45
MAX_RETURN_TEXT_CHARS = 500

# ========================================
# LOAD VECTORSTORE
# ========================================
print("📥 Đang load FAISS index và metadata...")

# Load chunks metadata
with open(CHUNKS_METADATA_FILE, "r", encoding="utf-8") as f:
    CHUNKS = json.load(f)

# Load FAISS index
index = faiss.read_index(FAISS_INDEX_FILE)

# Load model (dùng cùng model với embedding)
with open(INDEX_METADATA_FILE, "r", encoding="utf-8") as f:
    index_meta = json.load(f)

MODEL_NAME = index_meta["model_name"]
embedding_model = SentenceTransformer(MODEL_NAME)

print(f"✅ Loaded {len(CHUNKS)} chunks | FAISS index: {index.ntotal} vectors")
print(f"📌 Model: {MODEL_NAME}")

# Tạo map nhanh từ index → chunk
CHUNK_BY_ID = {i: chunk for i, chunk in enumerate(CHUNKS)}

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
# DOMAIN & OOS (có thể mở rộng sau)
# ========================================
OOS_KEYWORDS = [
    "thai sản", "bảo hiểm xã hội", "hợp đồng lao động", "nghỉ việc",
    "mũ bảo hiểm", "vượt đèn đỏ", "bằng lái", "công chứng",
    "di chúc", "thừa kế", "lừa đảo", "đánh nhau", "ly hôn"
]

def detect_out_of_scope(query: str, query_emb, top1_score: float):
    q_norm = normalize_text(query)

    # Keyword filter
    for kw in OOS_KEYWORDS:
        if kw in q_norm:
            return True, f"Câu hỏi thuộc lĩnh vực chưa được hỗ trợ ({kw})."

    # Top1 score filter
    if top1_score < STRICT_TOP1_THRESHOLD:
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
    """
    # Embedding query
    query_emb = embedding_model.encode(
        f"query: {query}",
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype(np.float32).reshape(1, -1)

    # FAISS Search
    scores, indices = index.search(query_emb, top_k)

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

        chunk = CHUNK_BY_ID.get(int(idx))
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
# TEST FUNCTION
# ========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTING LEGAL SEARCH")
    print("="*60)
    
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
