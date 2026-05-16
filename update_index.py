import os
import io
import json
import faiss
import numpy as np
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sentence_transformers import SentenceTransformer

# ====================================
# CẤU HÌNH
# ====================================
DRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "1RKqAib6xPISoaMmoBb2ywNJD4KEqdvAE")
INDEX_FILE       = "legal_index.faiss"
METADATA_FILE    = "metadata.json"   # lưu: [{"file": "103-2026-ND-CP.txt", "chunk": 0}, ...]
BGE_DIM          = 1024              # output dim của BAAI/bge-m3
CHUNK_SIZE       = 500               # số từ mỗi chunk
CHUNK_OVERLAP    = 50                # số từ overlap giữa các chunk

# ====================================
# 1. KẾT NỐI GOOGLE DRIVE
# ====================================
print("🔗 Đang kết nối Google Drive...")
try:
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    drive_service = build("drive", "v3", credentials=creds)
    print("✅ Kết nối thành công.")
except Exception as e:
    raise SystemExit(f"❌ Lỗi kết nối Google Drive: {e}")

# ====================================
# 2. LẤY DANH SÁCH FILE TRÊN DRIVE
# ====================================
print("🔍 Đang quét thư mục Drive...")
results = drive_service.files().list(
    q=f"'{DRIVE_FOLDER_ID}' in parents and trashed = false",
    fields="files(id, name)"
).execute()
files = results.get("files", [])

if not files:
    raise SystemExit("✨ Thư mục Drive trống. Dừng.")

# ====================================
# 3. LỌC FILE CHƯA ĐƯỢC INDEX (tránh trùng lặp)
# ====================================
# metadata là list các dict: {"file": tên_file, "chunk": số_thứ_tự_chunk}
if os.path.exists(METADATA_FILE):
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata: list[dict] = json.load(f)
else:
    metadata = []

da_index = {entry["file"] for entry in metadata}  # tên file đã index
files_moi = [f for f in files if f["name"].endswith(".txt") and f["name"] not in da_index]

if not files_moi:
    raise SystemExit("✨ Không có văn bản mới. Index đã cập nhật.")

print(f"📄 Tìm thấy {len(files_moi)} file mới: {[f['name'] for f in files_moi]}")

# ====================================
# 4. TẢI VÀ CHUNK VĂN BẢN
# ====================================
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Chia văn bản thành các đoạn nhỏ có overlap."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), size - overlap):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

all_chunks   = []  # nội dung text của từng chunk
new_metadata = []  # metadata tương ứng từng chunk

for file in files_moi:
    print(f"  ⬇️  Đang tải: {file['name']}")
    try:
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(
            fh, drive_service.files().get_media(fileId=file["id"])
        )
        done = False
        while not done:
            _, done = downloader.next_chunk()

        text   = fh.getvalue().decode("utf-8")
        chunks = chunk_text(text)

        if not chunks:
            print(f"  ⚠️  File rỗng, bỏ qua: {file['name']}")
            continue

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            new_metadata.append({"file": file["name"], "chunk": i})

        print(f"      → {len(chunks)} chunks")

    except Exception as e:
        print(f"  ❌ Lỗi tải {file['name']}: {e}")

if not all_chunks:
    raise SystemExit("⚠️ Không có chunk nào hợp lệ để xử lý.")

# ====================================
# 5. ENCODE SANG VECTOR
# ====================================
print(f"\n🧠 Đang encode {len(all_chunks)} chunks với BAAI/bge-m3...")
model      = SentenceTransformer("BAAI/bge-m3", device="cpu")
new_vectors = model.encode(
    all_chunks,
    normalize_embeddings=True,
    batch_size=32,
    show_progress_bar=True
)
new_vectors = np.array(new_vectors, dtype="float32")

# ====================================
# 6. LOAD HOẶC TẠO MỚI FAISS INDEX
# ====================================
if os.path.exists(INDEX_FILE):
    print(f"📂 Đang nạp index hiện tại ({INDEX_FILE})...")
    index = faiss.read_index(INDEX_FILE)
else:
    print(f"🆕 Chưa có index, tạo mới IndexFlatIP (dim={BGE_DIM})...")
    index = faiss.IndexFlatIP(BGE_DIM)

# ====================================
# 7. THÊM VECTOR VÀ LƯU
# ====================================
index.add(new_vectors)
faiss.write_index(index, INDEX_FILE)
print(f"💾 Đã lưu index: {INDEX_FILE} ({index.ntotal} vectors tổng cộng)")

metadata.extend(new_metadata)
with open(METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)
print(f"💾 Đã lưu metadata: {METADATA_FILE} ({len(metadata)} chunks tổng cộng)")

print(f"\n✅ Hoàn tất! Đã thêm {len(new_vectors)} vectors từ {len(files_moi)} văn bản mới.")
