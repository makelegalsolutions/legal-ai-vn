import os
import re
import json
import hashlib
import numpy as np
import faiss
import torch
import shutil
from datetime import datetime
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ========================================
# CONFIG
# ========================================
CHUNKS_LATEST = "data/chunks/legal_chunks_latest.json"
VECTORSTORE_DIR = "data/vectorstore"

BATCH_SIZE = 32
MODEL_NAME = "intfloat/multilingual-e5-base"

CHECKPOINT_FILE = os.path.join(VECTORSTORE_DIR, "embeddings_checkpoint.npz")
EMBEDDINGS_FILE = os.path.join(VECTORSTORE_DIR, "embeddings.npy")
FAISS_INDEX_FILE = os.path.join(VECTORSTORE_DIR, "legal_index.faiss")
CHUNKS_METADATA_FILE = os.path.join(VECTORSTORE_DIR, "chunks_metadata.json")
INDEX_METADATA_FILE = os.path.join(VECTORSTORE_DIR, "index_metadata.json")

CHECKPOINT_EVERY_N_BATCHES = 8
MAX_RETRIEVAL_TEXT_CHARS = 1800

# Index type
USE_HNSW = False  # False = Exact (IndexFlatIP) - khuyến nghị cho pháp luật

os.makedirs(VECTORSTORE_DIR, exist_ok=True)

# ========================================
# LOAD CHUNKS FROM PREVIOUS STEP
# ========================================
if not os.path.exists(CHUNKS_LATEST):
    print("❌ Không tìm thấy legal_chunks_latest.json")
    print("Vui lòng chạy chunking_pipeline.py trước!")
    exit(1)

with open(CHUNKS_LATEST, "r", encoding="utf-8") as f:
    CHUNKS = json.load(f)

print(f"📥 Đã load {len(CHUNKS)} chunks để tạo embedding.")

# ========================================
# SORT CHUNKS
# ========================================
CHUNKS.sort(key=lambda x: x.get("chunk_id", ""))

# ========================================
# DATASET SIGNATURE (để resume & detect thay đổi)
# ========================================
content_for_hash = "||".join(
    f"{chunk.get('chunk_id')}:{chunk.get('text', '')[:800]}"
    for chunk in CHUNKS
)
dataset_signature = hashlib.md5(content_for_hash.encode("utf-8")).hexdigest()
print(f"🧩 Dataset signature: {dataset_signature[:16]}...")

# ========================================
# BUILD RETRIEVAL TEXT
# ========================================
long_chunks = 0

for chunk in CHUNKS:
    if chunk.get("retrieval_text"):
        continue

    retrieval_parts = []

    if chunk.get("doc_id"):
        retrieval_parts.append(f"Văn bản {chunk['doc_id']}.")
    if chunk.get("version_id"):
        retrieval_parts.append(f"VBHN {chunk['version_id']}.")
    if chunk.get("article"):
        retrieval_parts.append(f"{chunk['article']}.")
    if chunk.get("title"):
        retrieval_parts.append(chunk['title'])

    retrieval_parts.append(chunk.get("text", ""))

    retrieval_text = " ".join(retrieval_parts)
    retrieval_text = " ".join(retrieval_text.split())  # normalize space

    if len(retrieval_text) > MAX_RETRIEVAL_TEXT_CHARS:
        long_chunks += 1

    chunk["retrieval_text"] = retrieval_text

if long_chunks > 0:
    print(f"⚠️ {long_chunks} chunks vượt {MAX_RETRIEVAL_TEXT_CHARS} ký tự.")

# ========================================
# DEVICE & MODEL
# ========================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🖥️  Device: {DEVICE} | Model: {MODEL_NAME}")

embedding_model = SentenceTransformer(MODEL_NAME, device=DEVICE)
EMBEDDING_DIM = embedding_model.get_sentence_embedding_dimension()
print(f"📐 Embedding dimension: {EMBEDDING_DIM}")

# ========================================
# PREPARE TEXTS FOR EMBEDDING
# ========================================
chunk_texts = ["passage: " + chunk["retrieval_text"] for chunk in CHUNKS]

print(f"📦 Tổng chunks cần encode: {len(chunk_texts)}")

# ========================================
# LOAD CHECKPOINT (nếu có)
# ========================================
base_embeddings = None
START_FROM = 0
new_batches = []

if os.path.exists(CHECKPOINT_FILE):
    try:
        saved = np.load(CHECKPOINT_FILE, allow_pickle=True)
        base_embeddings = saved["embeddings"]
        START_FROM = int(saved["last_index"])
        saved_sig = str(saved.get("dataset_signature", ""))

        if saved_sig and saved_sig != dataset_signature:
            raise ValueError("Dataset signature thay đổi → Xóa checkpoint và chạy lại.")

        print(f"⏩ Resume từ chunk {START_FROM}/{len(chunk_texts)}")
    except Exception as e:
        print(f"⚠️ Checkpoint lỗi: {e} → Chạy lại từ đầu.")
        base_embeddings = None
        START_FROM = 0

# ========================================
# ENCODING
# ========================================
for i in tqdm(range(START_FROM, len(chunk_texts), BATCH_SIZE), desc="🔄 Encoding"):
    batch = chunk_texts[i : i + BATCH_SIZE]

    batch_emb = embedding_model.encode(
        batch,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    )
    batch_emb = batch_emb.astype(np.float32)
    new_batches.append(batch_emb)

    current_index = min(i + BATCH_SIZE, len(chunk_texts))
    current_batch_num = (i // BATCH_SIZE) + 1

    # Save checkpoint
    if (current_batch_num % CHECKPOINT_EVERY_N_BATCHES == 0) or (current_index == len(chunk_texts)):
        new_part = np.vstack(new_batches)
        base_embeddings = np.vstack([base_embeddings, new_part]) if base_embeddings is not None else new_part

        np.savez(
            CHECKPOINT_FILE,
            embeddings=base_embeddings,
            last_index=current_index,
            dataset_signature=dataset_signature
        )
        np.save(EMBEDDINGS_FILE, base_embeddings)

        print(f"💾 Checkpoint saved at {current_index}/{len(chunk_texts)}")
        new_batches = []

# Final merge
if new_batches:
    new_part = np.vstack(new_batches)
    embeddings = np.vstack([base_embeddings, new_part]) if base_embeddings is not None else new_part
else:
    embeddings = base_embeddings

embeddings = embeddings.astype(np.float32)

# ========================================
# VALIDATION
# ========================================
if embeddings.shape[0] != len(CHUNKS):
    raise ValueError(f"❌ Số vector ({embeddings.shape[0]}) không khớp số chunk ({len(CHUNKS)})")

print(f"✅ Encoding hoàn tất: {embeddings.shape}")

# ========================================
# SAVE METADATA & EMBEDDINGS
# ========================================
np.save(EMBEDDINGS_FILE, embeddings)

with open(CHUNKS_METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(CHUNKS, f, ensure_ascii=False, indent=2)

# Index metadata
index_metadata = {
    "model_name": MODEL_NAME,
    "embedding_dim": int(EMBEDDING_DIM),
    "total_chunks": len(CHUNKS),
    "dataset_signature": dataset_signature,
    "faiss_index_type": "IndexFlatIP" if not USE_HNSW else "IndexHNSWFlat",
    "normalized": True,
    "created_at": datetime.now().isoformat(),
    "max_retrieval_chars": MAX_RETRIEVAL_TEXT_CHARS
}

with open(INDEX_METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(index_metadata, f, ensure_ascii=False, indent=2)

# ========================================
# BUILD FAISS INDEX
# ========================================
print("🔨 Đang xây dựng FAISS index...")

if USE_HNSW:
    index = faiss.IndexHNSWFlat(EMBEDDING_DIM, 64)
    index.hnsw.efConstruction = 200
    index.hnsw.efSearch = 128
    print("⚠️ Sử dụng IndexHNSWFlat (Approximate)")
else:
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    print("✅ Sử dụng IndexFlatIP (Exact - phù hợp pháp luật)")

index.add(embeddings)
faiss.write_index(index, FAISS_INDEX_FILE)

print(f"✅ FAISS index saved: {FAISS_INDEX_FILE}")
print(f"📊 Total vectors in index: {index.ntotal}")

# ========================================
# CREATE VERSIONED COPY FOR HOT-SWAP
# ========================================
version = datetime.now().strftime("%Y%m%d_%H%M%S")
VERSIONED_FAISS = os.path.join(VECTORSTORE_DIR, f"legal_index_{version}.faiss")
VERSIONED_METADATA = os.path.join(VECTORSTORE_DIR, f"index_metadata_{version}.json")
VERSIONED_CHUNKS = os.path.join(VECTORSTORE_DIR, f"chunks_metadata_{version}.json")

# Copy versioned files
shutil.copy2(FAISS_INDEX_FILE, VERSIONED_FAISS)
shutil.copy2(INDEX_METADATA_FILE, VERSIONED_METADATA)
shutil.copy2(CHUNKS_METADATA_FILE, VERSIONED_CHUNKS)

# Update latest version pointer
with open(os.path.join(VECTORSTORE_DIR, "latest_version.txt"), "w") as f:
    f.write(version)

print(f"📌 Version {version} created for hot-swap")
print(f"   → {VERSIONED_FAISS}")

# ========================================
# UPLOAD TO GOOGLE DRIVE (PHẦN THÊM MỚI)
# ========================================
try:
    from .faiss_drive_manager import save_faiss_version_to_drive, clean_old_versions
    
    FAISS_DRIVE_FOLDER_ID = os.environ.get("FAISS_DRIVE_FOLDER_ID")
    
    if FAISS_DRIVE_FOLDER_ID:
        print("\n📤 Uploading FAISS to Google Drive...")
        uploaded_version = save_faiss_version_to_drive(FAISS_DRIVE_FOLDER_ID)
        if uploaded_version:
            print(f"✅ Uploaded version: {uploaded_version}")
        
        # Dọn dẹp version cũ (giữ 5 bản)
        clean_old_versions(FAISS_DRIVE_FOLDER_ID, keep=5)
    else:
        print("⚠️ FAISS_DRIVE_FOLDER_ID not set, skipping Drive upload")
except ImportError:
    print("⚠️ faiss_drive_manager not found, skipping Drive upload")
except Exception as e:
    print(f"⚠️ Failed to upload to Drive: {e}")

print("=" * 70)
print("🎉 VECTOR PIPELINE HOÀN THÀNH!")
print(f"📁 Vectorstore folder: {VECTORSTORE_DIR}")
print("=" * 70)
