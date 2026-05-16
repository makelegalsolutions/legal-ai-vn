import os, io, json, faiss
import numpy as np
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sentence_transformers import SentenceTransformer

DRIVE_FOLDER_ID = "1RKqAib6xPISoaMmoBb2ywNJD4KEqdvAE"
METADATA_FILE   = "metadata.json"
INDEX_FILE      = "legal_index.faiss"
BGE_DIM         = 1024  # output dim của BAAI/bge-m3

# 1. Kết nối Drive
try:
    info  = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    svc = build("drive", "v3", credentials=creds)
except Exception as e:
    raise SystemExit(f"❌ Lỗi kết nối Drive: {e}")

# 2. Lấy danh sách file trên Drive
files = svc.files().list(
    q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name)"
).execute().get("files", [])

# 3. Load metadata hiện tại (tên file đã index)
metadata = json.load(open(METADATA_FILE)) if os.path.exists(METADATA_FILE) else []
da_index = set(metadata)

# 4. Lọc file chưa index
files_moi = [f for f in files if f["name"].endswith(".txt") and f["name"] not in da_index]
if not files_moi:
    print("✨ Không có văn bản mới. Dừng.")
    raise SystemExit(0)

print(f"📄 Tìm thấy {len(files_moi)} file mới cần xử lý")

# 5. Tải và chunk văn bản
def chunk_text(text, size=500, overlap=50):
    words = text.split()
    return [" ".join(words[i:i+size]) for i in range(0, len(words), size - overlap)]

all_chunks  = []
chunk_names = []  # tên file tương ứng với mỗi chunk

for f in files_moi:
    print(f"  ⬇️  {f['name']}")
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, svc.files().get_media(fileId=f["id"]))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text   = fh.getvalue().decode("utf-8")
    chunks = chunk_text(text)
    all_chunks.extend(chunks)
    chunk_names.extend([f["name"]] * len(chunks))

# 6. Encode
print("🧠 Đang encode vectors...")
model   = SentenceTransformer("BAAI/bge-m3", device="cpu")
vectors = model.encode(all_chunks, normalize_embeddings=True, show_progress_bar=True)
vectors = np.array(vectors, dtype="float32")

# 7. Load hoặc tạo mới FAISS index
if os.path.exists(INDEX_FILE):
    index = faiss.read_index(INDEX_FILE)
else:
    index = faiss.IndexFlatIP(BGE_DIM)

index.add(vectors)
faiss.write_index(index, INDEX_FILE)

# 8. Cập nhật metadata (thêm tên file + chunk mapping)
metadata.extend(chunk_names)
json.dump(metadata, open(METADATA_FILE, "w"), ensure_ascii=False)

print(f"✅ Đã thêm {len(vectors)} vectors từ {len(files_moi)} văn bản mới.")
