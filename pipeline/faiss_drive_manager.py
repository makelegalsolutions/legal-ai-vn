"""
Quản lý FAISS index trên Google Drive
Hỗ trợ upload, download, versioning
"""

import os
import json
import tempfile
from datetime import datetime
from typing import Optional

import gdown
import googleapiclient.discovery
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

# ========================================
# CONFIG
# ========================================
SERVICE_ACCOUNT_FILE = "service_account.json"
FAISS_DRIVE_FOLDER_ID = os.environ.get("FAISS_DRIVE_FOLDER_ID", "")
LOCAL_VECTORSTORE_DIR = "data/vectorstore"

os.makedirs(LOCAL_VECTORSTORE_DIR, exist_ok=True)


# ========================================
# GOOGLE DRIVE AUTH
# ========================================
def get_drive_service():
    """Tạo service để kết nối Google Drive"""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Không tìm thấy {SERVICE_ACCOUNT_FILE}")
    
    scopes = ["https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    service = googleapiclient.discovery.build("drive", "v3", credentials=credentials)
    return service


# ========================================
# UPLOAD FILE TO DRIVE
# ========================================
def upload_to_drive(local_path: str, drive_filename: str, folder_id: str) -> str:
    """Upload file lên Google Drive, trả về file ID"""
    if not os.path.exists(local_path):
        print(f"⚠️ File not found: {local_path}")
        return None
    
    service = get_drive_service()
    
    # Kiểm tra file đã tồn tại chưa
    query = f"name='{drive_filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    
    if files:
        # File đã tồn tại, xóa cũ
        file_id = files[0]["id"]
        service.files().delete(fileId=file_id).execute()
        print(f"🗑️ Deleted old: {drive_filename}")
    
    # Upload mới
    media = MediaFileUpload(local_path, resumable=True)
    file_metadata = {
        "name": drive_filename,
        "parents": [folder_id]
    }
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    
    print(f"📤 Uploaded: {drive_filename}")
    return file.get("id")


# ========================================
# DOWNLOAD FILE FROM DRIVE
# ========================================
def download_from_drive(file_id: str, local_path: str) -> bool:
    """Download file từ Google Drive về local"""
    try:
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, local_path, quiet=False)
        return os.path.exists(local_path)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


# ========================================
# GET LATEST VERSION FROM DRIVE
# ========================================
def get_latest_version_from_drive(folder_id: str) -> Optional[str]:
    """Đọc latest_version.txt từ Drive để biết version mới nhất"""
    if not folder_id:
        return None
    
    service = get_drive_service()
    
    # Tìm file latest_version.txt
    query = f"name='latest_version.txt' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    
    if not files:
        return None
    
    # Tải về đọc nội dung
    file_id = files[0]["id"]
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
        download_from_drive(file_id, tmp.name)
        with open(tmp.name, "r") as f:
            version = f.read().strip()
        os.unlink(tmp.name)
        return version
    
    return None


# ========================================
# UPDATE LATEST VERSION POINTER
# ========================================
def update_latest_version(folder_id: str, version: str):
    """Cập nhật file latest_version.txt trên Drive"""
    if not folder_id:
        return
    
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
        tmp.write(version)
        tmp.flush()
        upload_to_drive(tmp.name, "latest_version.txt", folder_id)
        os.unlink(tmp.name)
    
    print(f"📌 Updated latest version: {version}")


# ========================================
# SAVE FAISS VERSION TO DRIVE
# ========================================
def save_faiss_version_to_drive(folder_id: str) -> Optional[str]:
    """
    Lưu FAISS index hiện tại lên Google Drive
    Trả về version string
    """
    if not folder_id:
        print("⚠️ FAISS_DRIVE_FOLDER_ID not set, skipping Drive upload")
        return None
    
    version = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Các file cần upload
    files_to_upload = [
        ("legal_index.faiss", f"legal_index_{version}.faiss"),
        ("index_metadata.json", f"index_metadata_{version}.json"),
        ("chunks_metadata.json", f"chunks_metadata_{version}.json"),
    ]
    
    print(f"\n📤 Uploading FAISS version {version} to Google Drive...")
    
    for local_name, drive_name in files_to_upload:
        local_path = os.path.join(LOCAL_VECTORSTORE_DIR, local_name)
        if os.path.exists(local_path):
            upload_to_drive(local_path, drive_name, folder_id)
        else:
            print(f"⚠️ Skipping {local_name} (not found)")
    
    # Cập nhật latest version
    update_latest_version(folder_id, version)
    
    return version


# ========================================
# LOAD FAISS VERSION FROM DRIVE
# ========================================
def load_faiss_version_from_drive(folder_id: str, version: str = None) -> bool:
    """
    Tải FAISS index từ Drive về local
    Nếu version=None, tải version mới nhất
    """
    if not folder_id:
        print("⚠️ FAISS_DRIVE_FOLDER_ID not set, cannot load from Drive")
        return False
    
    service = get_drive_service()
    
    # Xác định version cần tải
    if version is None:
        version = get_latest_version_from_drive(folder_id)
        if not version:
            print("❌ No version found on Drive")
            return False
    
    print(f"📥 Loading FAISS version: {version}")
    
    # Các file cần tải
    files_to_download = [
        (f"legal_index_{version}.faiss", "legal_index.faiss"),
        (f"index_metadata_{version}.json", "index_metadata.json"),
        (f"chunks_metadata_{version}.json", "chunks_metadata.json"),
    ]
    
    success = True
    for drive_name, local_name in files_to_download:
        # Tìm file trên Drive
        query = f"name='{drive_name}' and '{folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        
        if not files:
            print(f"❌ File not found: {drive_name}")
            success = False
            continue
        
        file_id = files[0]["id"]
        local_path = os.path.join(LOCAL_VECTORSTORE_DIR, local_name)
        if not download_from_drive(file_id, local_path):
            success = False
    
    if success:
        # Lưu version hiện tại
        with open(os.path.join(LOCAL_VECTORSTORE_DIR, "current_version.txt"), "w") as f:
            f.write(version)
        print(f"✅ Loaded version {version}")
    else:
        print(f"❌ Failed to load version {version}")
    
    return success


# ========================================
# CLEAN OLD VERSIONS (giữ 5 bản gần nhất)
# ========================================
def clean_old_versions(folder_id: str, keep: int = 5):
    """Xóa các version cũ trên Drive, chỉ giữ lại `keep` bản gần nhất"""
    if not folder_id:
        return
    
    service = get_drive_service()
    
    # Lấy tất cả file FAISS index
    query = f"name contains 'legal_index_' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
    files = results.get("files", [])
    
    # Sắp xếp theo thời gian tạo (mới nhất trước)
    files.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
    
    # Xóa các file cũ
    for file in files[keep:]:
        service.files().delete(fileId=file["id"]).execute()
        print(f"🗑️ Deleted old: {file['name']}")
    
    # Cũng xóa metadata cũ
    for suffix in ["index_metadata_", "chunks_metadata_"]:
        query = f"name contains '{suffix}' and '{folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        files = results.get("files", [])
        files.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        for file in files[keep:]:
            service.files().delete(fileId=file["id"]).execute()
            print(f"🗑️ Deleted old: {file['name']}")


# ========================================
# CHECK IF FAISS EXISTS LOCALLY
# ========================================
def faiss_exists_locally() -> bool:
    """Kiểm tra file FAISS có tồn tại trong thư mục local không"""
    local_index = os.path.join(LOCAL_VECTORSTORE_DIR, "legal_index.faiss")
    return os.path.exists(local_index) and os.path.getsize(local_index) > 0


# ========================================
# ENSURE FAISS AVAILABLE
# ========================================
def ensure_faiss_available() -> bool:
    """
    Đảm bảo có FAISS index local, tải từ Drive nếu cần
    Trả về True nếu có FAISS sẵn sàng
    """
    if faiss_exists_locally():
        print("✅ FAISS found locally")
        return True
    
    # Thử tải từ Drive
    if FAISS_DRIVE_FOLDER_ID:
        print("📥 FAISS not found locally, downloading from Drive...")
        return load_faiss_version_from_drive(FAISS_DRIVE_FOLDER_ID)
    
    print("⚠️ No FAISS available locally or on Drive")
    return False
