import os
import json
import faiss
import numpy as np
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from sentence_transformers import SentenceTransformer

# ====================================
# CẤU HÌNH
# ====================================
DRIVE_FOLDER_ID = "1RKqAib6xPISoaMmoBb2ywNJD4KEqdvAE"
INDEX_FILE      = "legal_index.faiss"
METADATA_FILE   = "metadata.json"   # Lưu cấu trúc: [{"file": "luat-abc.txt", "chunk": 0, "text": "..."}]
BGE_DIM          = 1024              # Định dạng chiều của BAAI/bge-m3
CHUNK_SIZE       = 500               # Số từ mỗi chunk
CHUNK_OVERLAP    = 50                # Số từ gối đầu giữa các chunk

# ====================================
# 1. KẾT NỐI GOOGLE DRIVE BẰNG APP PASSWORD
# ====================================
print("🔗 Đang kết nối Google Drive qua App Password...")
try:
    gauth = GoogleAuth()
    gauth.auth_method = 'client'
    # Đăng nhập thẳng bằng tài khoản Gmail cá nhân cá nhân và mật khẩu ứng dụng
    gauth.credentials = gauth.auth.authenticate_user_credentials(
        username=os.environ["GMAIL_USER"],
        password=os.environ["GMAIL_PASSWORD"]
    )
    drive = GoogleDrive(gauth)
    print("✅ Kết nối thành công.")
except Exception as e:
    raise SystemExit(f"❌ Lỗi kết nối Google Drive: {e}")

# ====================================
# 2. LẤY DANH SÁCH FILE TRÊN DRIVE (Sử dụng PyDrive2)
# ====================================
print("🔍 Đang quét thư mục Drive...")
try:
    file_list = drive.ListFile({'q': f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"}).GetList()
except Exception as e:
    raise SystemExit(f"❌ Không thể đọc danh sách file từ thư mục Drive ID '{DRIVE_FOLDER_ID}': {e}")

if not file_list:
    raise SystemExit("✨ Thư mục Drive trống. Dừng.")

# ====================================
# 3. LỌC FILE CHƯA ĐƯỢC INDEX (Tránh trùng lặp dữ liệu)
# ====================================
if os.path.exists(METADATA_FILE):
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)
else:
    metadata = []

da_index = {entry["file"] for entry in metadata}  # Tập hợp tên các file đã chạy trước đó
files_moi = [f for f in file_list if f["title"].endswith(".txt") and f["title"] not in da_index]

if not files_moi:
    raise SystemExit("✨ Không có văn bản mới. Hệ thống FAISS đã được cập nhật tối tân nhất.")

print(f"📄 Tìm thấy {len(files_moi)} file mới: {[f['title'] for f in files_moi]}")

# ====================================
# 4. TẢI VÀ CHUNK VĂN BẢN (Lưu kèm nội dung text vào Metadata)
# ====================================
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), size - overlap):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

all_chunks   = []  
new_metadata = []  

for file in files_moi:
    file_name = file['title']
    print(f"  ⬇️  Đang tải: {file_name}")
    try:
        # Tải trực tiếp nội dung dạng chuỗi chữ từ Google Drive
        text = file.GetContentString(encoding="utf-8")
        chunks = chunk_text(text)

        if not chunks:
            print(f"  ⚠️  File rỗng, bỏ qua: {file_name}")
            continue

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            # Giữ nguyên cấu trúc yêu cầu của bạn: lưu kèm trường "text"
            new_metadata.append({"file": file_name, "chunk": i, "text": chunk})

        print(f"      → Đã băm thành {len(chunks)} chunks")

    except Exception as e:
        print(f"  ❌ Lỗi tải {file_name}: {e}")

if not all_chunks:
    raise SystemExit("⚠️ Không có dữ liệu chữ nào hợp lệ để xử lý tiếp.")

# ====================================
# 5. MÔ HÌNH HÓA SANG VECTOR
# ====================================
print(f"\n🧠 Đang encode {len(all_chunks)} chunks với BAAI/bge-m3...")
model       = SentenceTransformer("BAAI/bge-m3", device="cpu")
new_vectors = model.encode(
    all_chunks,
    normalize_embeddings=True,
    batch_size=32,
    show_progress_bar=True
)
new_vectors = np.array(new_vectors, dtype="float32")

# ====================================
# 6. KHỞI TẠO HOẶC ĐỌC TIẾP FAISS INDEX
# ====================================
if os.path.exists(INDEX_FILE):
    print(f"📂 Đang nạp cơ sở dữ liệu index hiện tại ({INDEX_FILE})...")
    index = faiss.read_index(INDEX_FILE)
else:
    print(f"🆕 Chưa có dữ liệu cũ, tiến hành khởi tạo cấu trúc IndexFlatIP gốc (dim={BGE_DIM})...")
    index = faiss.IndexFlatIP(BGE_DIM)

# ====================================
# 7. THÊM VECTOR VÀ LƯU GHI ĐÈ
# ====================================
index.add(new_vectors)
faiss.write_index(index, INDEX_FILE)
print(f"💾 Đã ghi nhận index: {INDEX_FILE} (Tổng cộng {index.ntotal} vectors lưu trên hệ thống)")

metadata.extend(new_metadata)
with open(METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)
print(f"💾 Đã cập nhật metadata mới: {METADATA_FILE} (Tổng cộng {len(metadata)} chunks)")

print(f"\n✅ Đường ống vận hành hoàn tất thành công!")
