"""
Incremental Update Pipeline - Chỉ xử lý file mới hoặc file thay đổi
Không chạy lại toàn bộ 3000 file mỗi lần
"""

import os
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple

# ========================================
# CONFIG
# ========================================
DATA_DIR = "data"
TEXTS_DIR = os.path.join(DATA_DIR, "texts")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
VECTORSTORE_DIR = os.path.join(DATA_DIR, "vectorstore")
STATE_FILE = os.path.join(DATA_DIR, "state", "processed_files.json")
INCREMENTAL_STATE = os.path.join(DATA_DIR, "state", "incremental_state.json")

# Files
CHUNKS_LATEST = os.path.join(CHUNKS_DIR, "legal_chunks_latest.json")
CHUNKS_METADATA = os.path.join(VECTORSTORE_DIR, "chunks_metadata.json")
FAISS_INDEX = os.path.join(VECTORSTORE_DIR, "legal_index.faiss")

os.makedirs(TEXTS_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)
os.makedirs(VECTORSTORE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)


# ========================================
# LOAD INCREMENTAL STATE
# ========================================
def load_incremental_state() -> Dict:
    """Load trạng thái incremental update"""
    if os.path.exists(INCREMENTAL_STATE):
        with open(INCREMENTAL_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "processed_files": {},  # file_name -> file_hash
        "last_full_build": None,
        "total_updates": 0
    }


def save_incremental_state(state: Dict):
    """Lưu trạng thái incremental update"""
    state["last_updated"] = datetime.now().isoformat()
    with open(INCREMENTAL_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ========================================
# FILE HASH
# ========================================
def get_file_hash(filepath: str) -> str:
    """Tính hash của file để phát hiện thay đổi"""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ========================================
# DETECT NEW/MODIFIED FILES
# ========================================
def detect_changes() -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Phát hiện file mới, file thay đổi, file bị xóa
    Returns: (new_files, modified_files, deleted_files)
    """
    # Load state
    incremental_state = load_incremental_state()
    processed = incremental_state.get("processed_files", {})
    
    # Load current processed files from validate
    if not os.path.exists(STATE_FILE):
        print("⚠️ No processed_files.json found. Run validate_pipeline first!")
        return set(), set(), set()
    
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        current_files = json.load(f)
    
    # Phát hiện thay đổi
    current_file_names = set(current_files.keys())
    old_file_names = set(processed.keys())
    
    new_files = current_file_names - old_file_names
    deleted_files = old_file_names - current_file_names
    
    # Phát hiện file thay đổi (size khác hoặc content thay đổi)
    modified_files = set()
    for file_name in current_file_names.intersection(old_file_names):
        old_hash = processed.get(file_name, {}).get("hash", "")
        # Tính hash mới
        filepath = os.path.join("data/downloads", file_name)
        if os.path.exists(filepath):
            new_hash = get_file_hash(filepath)
            if new_hash != old_hash:
                modified_files.add(file_name)
    
    print(f"\n📊 CHANGE DETECTION:")
    print(f"   New files     : {len(new_files)}")
    print(f"   Modified files: {len(modified_files)}")
    print(f"   Deleted files : {len(deleted_files)}")
    
    return new_files, modified_files, deleted_files


# ========================================
# LOAD EXISTING CHUNKS
# ========================================
def load_existing_chunks() -> Tuple[List[Dict], Dict[str, List[str]]]:
    """Load chunks hiện có và mapping file_name -> chunk_ids"""
    existing_chunks = []
    file_to_chunks = {}
    
    if os.path.exists(CHUNKS_LATEST):
        with open(CHUNKS_LATEST, "r", encoding="utf-8") as f:
            existing_chunks = json.load(f)
        
        # Build mapping
        for chunk in existing_chunks:
            file_name = chunk.get("file_name", "")
            if file_name:
                if file_name not in file_to_chunks:
                    file_to_chunks[file_name] = []
                file_to_chunks[file_name].append(chunk.get("chunk_id", ""))
    
    return existing_chunks, file_to_chunks


# ========================================
# PROCESS NEW/MODIFIED FILES ONLY
# ========================================
def process_file(file_name: str, texts: List[Dict]) -> List[Dict]:
    """Xử lý một file - tạo chunks cho file đó"""
    from chunking_pipeline import process_single_file
    
    # Tìm text của file
    file_text = None
    for item in texts:
        if item.get("source") == file_name:
            file_text = item.get("text", "")
            break
    
    if not file_text:
        return []
    
    # Gọi hàm chunking cho file (cần export từ chunking_pipeline)
    try:
        from chunking_pipeline import process_single_file as chunk_single
        chunks = chunk_single(file_name, file_text)
        return chunks
    except ImportError:
        # Fallback chunking đơn giản
        return fallback_chunking(file_name, file_text)


def fallback_chunking(file_name: str, text: str) -> List[Dict]:
    """Chunking đơn giản fallback"""
    import re
    chunks = []
    
    # Tách theo Điều
    articles = re.split(r'(Điều\s+\d+[A-Za-z0-9\-]*)', text)
    
    for i in range(1, len(articles), 2):
        if i+1 < len(articles):
            article_title = articles[i].strip()
            article_content = articles[i+1].strip()
            
            chunks.append({
                "chunk_id": f"{file_name}::{article_title}_{i}",
                "doc_id": file_name.replace(".pdf", "").replace(".docx", ""),
                "file_name": file_name,
                "article": article_title,
                "title": file_name,
                "text": article_content[:2000]
            })
    
    return chunks


# ========================================
# UPDATE FAISS INDEX (Append new vectors)
# ========================================
def update_faiss_index(new_chunks: List[Dict]) -> bool:
    """Append new vectors vào FAISS index hiện có"""
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer
    
    if not new_chunks:
        return True
    
    # Load model
    model = SentenceTransformer("intfloat/multilingual-e5-base")
    
    # Tạo retrieval text cho chunks mới
    for chunk in new_chunks:
        retrieval_parts = [
            f"Văn bản {chunk.get('doc_id', '')}.",
            chunk.get('article', ''),
            chunk.get('text', '')
        ]
        chunk["retrieval_text"] = " ".join([p for p in retrieval_parts if p])
    
    # Encode
    texts = ["passage: " + chunk["retrieval_text"] for chunk in new_chunks]
    new_embeddings = model.encode(texts, normalize_embeddings=True)
    new_embeddings = new_embeddings.astype(np.float32)
    
    # Load existing index hoặc tạo mới
    if os.path.exists(FAISS_INDEX):
        index = faiss.read_index(FAISS_INDEX)
        print(f"✅ Loaded existing index with {index.ntotal} vectors")
    else:
        dim = new_embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        print(f"✅ Created new index (dim={dim})")
    
    # Append
    index.add(new_embeddings)
    faiss.write_index(index, FAISS_INDEX)
    
    print(f"✅ Index updated: now {index.ntotal} vectors")
    return True


# ========================================
# UPDATE CHUNKS FILE (Merge)
# ========================================
def update_chunks_file(new_chunks: List[Dict], modified_files: Set[str], deleted_files: Set[str]):
    """Cập nhật file chunks: thêm mới, cập nhật, xóa"""
    existing_chunks, file_to_chunks = load_existing_chunks()
    
    # Xóa chunks của file đã xóa hoặc sửa đổi
    files_to_remove = deleted_files.union(modified_files)
    for file_name in files_to_remove:
        if file_name in file_to_chunks:
            chunk_ids_to_remove = set(file_to_chunks[file_name])
            existing_chunks = [c for c in existing_chunks if c.get("chunk_id") not in chunk_ids_to_remove]
            print(f"   Removed {len(chunk_ids_to_remove)} chunks from {file_name}")
    
    # Thêm chunks mới (của file mới và file sửa đổi)
    existing_chunks.extend(new_chunks)
    
    # Lưu
    with open(CHUNKS_LATEST, "w", encoding="utf-8") as f:
        json.dump(existing_chunks, f, ensure_ascii=False, indent=2)
    
    # Cũng lưu vào vectorstore
    with open(CHUNKS_METADATA, "w", encoding="utf-8") as f:
        json.dump(existing_chunks, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Chunks updated: total {len(existing_chunks)} chunks")
    return existing_chunks


# ========================================
# CREATE VERSIONED BACKUP
# ========================================
def create_versioned_backup():
    """Tạo bản sao versioned của FAISS và chunks"""
    version = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if os.path.exists(FAISS_INDEX):
        shutil.copy2(FAISS_INDEX, os.path.join(VECTORSTORE_DIR, f"legal_index_{version}.faiss"))
    
    if os.path.exists(CHUNKS_METADATA):
        shutil.copy2(CHUNKS_METADATA, os.path.join(VECTORSTORE_DIR, f"chunks_metadata_{version}.json"))
    
    # Update latest version pointer
    with open(os.path.join(VECTORSTORE_DIR, "latest_version.txt"), "w") as f:
        f.write(version)
    
    print(f"📌 Versioned backup: {version}")
    return version


# ========================================
# MAIN INCREMENTAL UPDATE
# ========================================
def run_incremental_update():
    """Chạy incremental update pipeline"""
    
    print("=" * 70)
    print("🔄 INCREMENTAL UPDATE PIPELINE")
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Bước 1: Detect changes
    new_files, modified_files, deleted_files = detect_changes()
    
    if not new_files and not modified_files and not deleted_files:
        print("\n📭 No changes detected. Nothing to update.")
        return True
    
    # Bước 2: Load texts for new/modified files
    texts_file = os.path.join(TEXTS_DIR, "legal_texts_latest.json")
    if not os.path.exists(texts_file):
        print("❌ No texts found. Run text_processing.py first!")
        return False
    
    with open(texts_file, "r", encoding="utf-8") as f:
        all_texts = json.load(f)
    
    # Bước 3: Process new and modified files
    all_new_chunks = []
    files_to_process = new_files.union(modified_files)
    
    for file_name in files_to_process:
        print(f"\n📄 Processing: {file_name}")
        chunks = process_file(file_name, all_texts)
        all_new_chunks.extend(chunks)
        print(f"   → {len(chunks)} chunks created")
    
    # Bước 4: Update chunks file
    update_chunks_file(all_new_chunks, modified_files, deleted_files)
    
    # Bước 5: Update FAISS index
    update_faiss_index(all_new_chunks)
    
    # Bước 6: Create versioned backup
    version = create_versioned_backup()
    
    # Bước 7: Update incremental state
    incremental_state = load_incremental_state()
    
    # Update hashes for processed files
    for file_name in new_files.union(modified_files):
        filepath = os.path.join("data/downloads", file_name)
        if os.path.exists(filepath):
            incremental_state["processed_files"][file_name] = {
                "hash": get_file_hash(filepath),
                "last_processed": datetime.now().isoformat(),
                "chunks": len([c for c in all_new_chunks if c.get("file_name") == file_name])
            }
    
    # Remove deleted files from state
    for file_name in deleted_files:
        if file_name in incremental_state["processed_files"]:
            del incremental_state["processed_files"][file_name]
    
    incremental_state["total_updates"] += 1
    save_incremental_state(incremental_state)
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ INCREMENTAL UPDATE COMPLETED")
    print(f"   New files     : {len(new_files)}")
    print(f"   Modified files: {len(modified_files)}")
    print(f"   Deleted files : {len(deleted_files)}")
    print(f"   New chunks    : {len(all_new_chunks)}")
    print(f"   Version       : {version}")
    print("=" * 70)
    
    return True


# ========================================
# FORCE FULL REBUILD (khi cần)
# ========================================
def force_full_rebuild():
    """Force rebuild toàn bộ (dùng khi cần)"""
    print("🔥 FORCE FULL REBUILD - Processing all files")
    
    # Xóa state incremental để rebuild từ đầu
    if os.path.exists(INCREMENTAL_STATE):
        os.remove(INCREMENTAL_STATE)
    
    # Chạy full pipeline
    os.system("python run_pipeline.py")
    
    # Reset incremental state
    incremental_state = {
        "processed_files": {},
        "last_full_build": datetime.now().isoformat(),
        "total_updates": 0
    }
    save_incremental_state(incremental_state)
    
    print("✅ Full rebuild completed")


# ========================================
# MAIN
# ========================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        force_full_rebuild()
    else:
        run_incremental_update()
