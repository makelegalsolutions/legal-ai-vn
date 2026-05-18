"""
Quản lý FAISS index trên Google Drive
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

SERVICE_ACCOUNT_FILE = "service_account.json"
LOCAL_VECTORSTORE_DIR = "data/vectorstore"

os.makedirs(LOCAL_VECTORSTORE_DIR, exist_ok=True)


def get_drive_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Không tìm thấy {SERVICE_ACCOUNT_FILE}")
    scopes = ["https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    return googleapiclient.discovery.build("drive", "v3", credentials=credentials)


def upload_to_drive(local_path: str, drive_filename: str, folder_id: str) -> str:
    if not os.path.exists(local_path):
        return None
    service = get_drive_service()
    query = f"name='{drive_filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        service.files().delete(fileId=files[0]["id"]).execute()
    media = MediaFileUpload(local_path, resumable=True)
    file_metadata = {"name": drive_filename, "parents": [folder_id]}
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file.get("id")


def download_from_drive(file_id: str, local_path: str) -> bool:
    try:
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, local_path, quiet=False)
        return os.path.exists(local_path)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


def get_latest_version_from_drive(folder_id: str) -> Optional[str]:
    if not folder_id:
        return None
    service = get_drive_service()
    query = f"name='latest_version.txt' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if not files:
        return None
    file_id = files[0]["id"]
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
        download_from_drive(file_id, tmp.name)
        with open(tmp.name, "r") as f:
            version = f.read().strip()
        os.unlink(tmp.name)
        return version
    return None


def update_latest_version(folder_id: str, version: str):
    if not folder_id:
        return
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
        tmp.write(version)
        tmp.flush()
        upload_to_drive(tmp.name, "latest_version.txt", folder_id)
        os.unlink(tmp.name)


def save_faiss_version_to_drive(folder_id: str) -> Optional[str]:
    if not folder_id:
        return None
    version = datetime.now().strftime("%Y%m%d_%H%M%S")
    files_to_upload = [
        ("legal_index.faiss", f"legal_index_{version}.faiss"),
        ("index_metadata.json", f"index_metadata_{version}.json"),
        ("chunks_metadata.json", f"chunks_metadata_{version}.json"),
    ]
    for local_name, drive_name in files_to_upload:
        local_path = os.path.join(LOCAL_VECTORSTORE_DIR, local_name)
        if os.path.exists(local_path):
            upload_to_drive(local_path, drive_name, folder_id)
    update_latest_version(folder_id, version)
    return version


def load_faiss_version_from_drive(folder_id: str, version: str = None) -> bool:
    """Tải FAISS index từ Google Drive về local"""
    if not folder_id:
        print("⚠️ FAISS_DRIVE_FOLDER_ID not set")
        return False
    
    try:
        from google.colab import drive
        drive.mount('/content/drive', force_remount=False)
        
        import shutil
        source = f"/content/drive/MyDrive/legal-ai-faiss/legal_index.faiss"
        dest = "data/vectorstore/legal_index.faiss"
        
        if os.path.exists(source):
            os.makedirs("data/vectorstore", exist_ok=True)
            shutil.copy2(source, dest)
            print(f"✅ Copied FAISS from Drive: {source}")
            return True
        else:
            print(f"❌ FAISS not found at: {source}")
            print("   Please upload FAISS to: My Drive/legal-ai-faiss/")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def clean_old_versions(folder_id: str, keep: int = 5):
    if not folder_id:
        return
    service = get_drive_service()
    query = f"name contains 'legal_index_' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
    files = results.get("files", [])
    files.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
    for file in files[keep:]:
        service.files().delete(fileId=file["id"]).execute()
        print(f"🗑️ Deleted old: {file['name']}")


print("✅ faiss_drive_manager.py loaded")
print("   Functions: load_faiss_version_from_drive, save_faiss_version_to_drive")
