import os
import json
from pathlib import Path

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

from docx import Document
from PyPDF2 import PdfReader


# ========================================
# CONFIG
# ========================================

DOWNLOAD_DIR = "data/downloads"
STATE_FILE = "data/state/processed_files.json"

MIN_TEXT_LENGTH = 500  # Tối thiểu 500 ký tự text thực

ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx"
]

SERVICE_ACCOUNT_FILE = "service_account.json"

DRIVE_FOLDER_ID = os.environ.get(
    "DRIVE_FOLDER_ID"
)


# ========================================
# CREATE FOLDERS
# ========================================

Path(DOWNLOAD_DIR).mkdir(
    parents=True,
    exist_ok=True
)

Path("data/state").mkdir(
    parents=True,
    exist_ok=True
)

Path("data/logs").mkdir(
    parents=True,
    exist_ok=True
)


# ========================================
# LOAD STATE
# ========================================

if os.path.exists(STATE_FILE):

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        PROCESSED = json.load(f)

else:

    PROCESSED = {}


# ========================================
# GOOGLE DRIVE AUTH
# ========================================

scope = [
    "https://www.googleapis.com/auth/drive"
]

credentials = (
    ServiceAccountCredentials
    .from_json_keyfile_name(
        SERVICE_ACCOUNT_FILE,
        scope
    )
)

GAUTH = GoogleAuth()
GAUTH.credentials = credentials

DRIVE = GoogleDrive(GAUTH)


# ========================================
# FILTER EXTENSION
# ========================================

def is_valid_extension(filename):

    ext = Path(filename).suffix.lower()

    return ext in ALLOWED_EXTENSIONS


# ========================================
# FILE INTEGRITY CHECK
# ========================================

def integrity_check(filepath):

    try:

        size = os.path.getsize(filepath)

        if size < 10000:  # Ít nhất 10KB

            return False, "FILE TOO SMALL"

        return True, None

    except Exception as e:

        return False, str(e)


# ========================================
# CHECK PDF HAS REAL TEXT (NOT SCAN)
# ========================================

def check_pdf_has_text(filepath: str, min_text_length: int = MIN_TEXT_LENGTH) -> tuple:
    """
    Kiểm tra PDF có text thực sự (không phải file scan)
    Trả về: (is_valid, text_or_error)
    """
    try:

        reader = PdfReader(filepath)

        if reader.is_encrypted:

            return False, "ENCRYPTED PDF"

        text = ""

        for page in reader.pages[:15]:  # Kiểm tra 15 trang đầu

            extracted = page.extract_text()

            if extracted:

                text += extracted + "\n"

        if len(text.strip()) < min_text_length:

            return False, f"INSUFFICIENT TEXT ({len(text)} chars)"

        return True, text

    except Exception as e:

        return False, str(e)


# ========================================
# CHECK DOCX HAS REAL TEXT
# ========================================

def check_docx_has_text(filepath: str, min_text_length: int = MIN_TEXT_LENGTH) -> tuple:
    """
    Kiểm tra DOCX có text thực sự
    Trả về: (is_valid, text_or_error)
    """
    try:

        doc = Document(filepath)

        paragraphs = [p.text for p in doc.paragraphs]

        text = "\n".join(paragraphs)

        if len(text.strip()) < min_text_length:

            return False, f"INSUFFICIENT TEXT ({len(text)} chars)"

        return True, text

    except Exception as e:

        return False, str(e)


# ========================================
# VALIDATE DOCX (full pipeline)
# ========================================

def validate_docx(filepath):

    ok, result = check_docx_has_text(filepath)

    if ok:

        return True, result

    else:

        return False, result


# ========================================
# VALIDATE PDF (full pipeline)
# ========================================

def validate_pdf(filepath):

    ok, result = check_pdf_has_text(filepath)

    if ok:

        return True, result

    else:

        return False, result


# ========================================
# RESULT CONTAINERS
# ========================================

DOCX_OK = []
DOCX_ERROR = []

PDF_OK = []
PDF_ERROR = []

SKIPPED_FILES = []


# ========================================
# SCAN GOOGLE DRIVE
# ========================================

print("=" * 70)
print("🔍 VALIDATION PIPELINE - GOOGLE DRIVE")
print("=" * 70)

query = (
    f"'{DRIVE_FOLDER_ID}' in parents "
    f"and trashed=false"
)

DRIVE_FILES = DRIVE.ListFile(
    {'q': query}
).GetList()

print(f"📁 Tìm thấy {len(DRIVE_FILES)} files trên Google Drive")


# ========================================
# DOWNLOAD NEW FILES
# ========================================

ALL_FILES = []

for drive_file in DRIVE_FILES:

    original_name = drive_file["title"]

    if not is_valid_extension(original_name):

        print(f"⏭️  Bỏ qua (không phải PDF/DOCX): {original_name}")
        continue

    file_size = int(
        drive_file.get("fileSize", 0)
    )

    # Kiểm tra file đã xử lý chưa (dựa trên tên và kích thước)
    if original_name in PROCESSED:

        old_size = PROCESSED[
            original_name
        ].get("size", 0)

        if old_size == file_size:

            print(f"⏭️  Bỏ qua (đã xử lý, không thay đổi): {original_name}")
            SKIPPED_FILES.append(original_name)
            continue

        else:
            print(f"🔄 File thay đổi kích thước: {original_name} (cũ: {old_size}, mới: {file_size})")

    save_path = os.path.join(
        DOWNLOAD_DIR,
        original_name
    )

    print(f"📥 Đang tải: {original_name} ({file_size} bytes)")

    drive_file.GetContentFile(save_path)

    ALL_FILES.append({
        "filename": original_name,
        "filepath": save_path,
        "size": file_size
    })


# ========================================
# PROCESS FILES
# ========================================

print("\n" + "=" * 70)
print("🔬 ĐANG VALIDATE NỘI DUNG FILE...")
print("=" * 70)

for file_info in ALL_FILES:

    filename = file_info["filename"]
    filepath = file_info["filepath"]
    file_size = file_info["size"]

    print(f"\n📄 Đang kiểm tra: {filename}")

    # =========================
    # FILE INTEGRITY CHECK
    # =========================

    ok, message = integrity_check(
        filepath
    )

    if not ok:

        print(f"   ❌ Integrity check failed: {message}")

        if filename.lower().endswith(
            ".docx"
        ):

            DOCX_ERROR.append({
                "file": filename,
                "error": message
            })

        elif filename.lower().endswith(
            ".pdf"
        ):

            PDF_ERROR.append({
                "file": filename,
                "error": message
            })

        # Xóa file lỗi
        os.remove(filepath)
        continue

    # =========================
    # VALIDATE DOCX
    # =========================

    if filename.lower().endswith(
        ".docx"
    ):

        ok, result = validate_docx(
            filepath
        )

        if ok:

            print(f"   ✅ DOCX hợp lệ - {len(result)} ký tự text")

            DOCX_OK.append({
                "file": filename,
                "size": file_size,
                "text_length": len(result)
            })

            PROCESSED[filename] = {
                "size": file_size,
                "text_length": len(result),
                "type": "docx",
                "validated_at": str(Path(filepath).stat().st_mtime)
            }

        else:

            print(f"   ❌ DOCX không hợp lệ: {result}")

            DOCX_ERROR.append({
                "file": filename,
                "error": result
            })

            # Xóa file không hợp lệ
            os.remove(filepath)

    # =========================
    # VALIDATE PDF
    # =========================

    elif filename.lower().endswith(
        ".pdf"
    ):

        ok, result = validate_pdf(
            filepath
        )

        if ok:

            print(f"   ✅ PDF hợp lệ - {len(result)} ký tự text")

            PDF_OK.append({
                "file": filename,
                "size": file_size,
                "text_length": len(result)
            })

            PROCESSED[filename] = {
                "size": file_size,
                "text_length": len(result),
                "type": "pdf",
                "validated_at": str(Path(filepath).stat().st_mtime)
            }

        else:

            print(f"   ❌ PDF không hợp lệ: {result}")

            PDF_ERROR.append({
                "file": filename,
                "error": result
            })

            # Xóa file không hợp lệ
            os.remove(filepath)


# ========================================
# SAVE STATE
# ========================================

with open(
    STATE_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        PROCESSED,
        f,
        ensure_ascii=False,
        indent=2
    )


# ========================================
# FINAL REPORT
# ========================================

print("\n" + "=" * 70)
print("📊 VALIDATION SUMMARY")
print("=" * 70)

print(f"\n✅ HỢP LỆ:")
print(f"   DOCX OK     : {len(DOCX_OK)} files")
for item in DOCX_OK:
    print(f"      - {item['file']} ({item['text_length']} chars)")

print(f"   PDF OK      : {len(PDF_OK)} files")
for item in PDF_OK:
    print(f"      - {item['file']} ({item['text_length']} chars)")

print(f"\n❌ LỖI:")
print(f"   DOCX ERROR  : {len(DOCX_ERROR)} files")
for item in DOCX_ERROR:
    print(f"      - {item['file']}: {item['error']}")

print(f"   PDF ERROR   : {len(PDF_ERROR)} files")
for item in PDF_ERROR:
    print(f"      - {item['file']}: {item['error']}")

print(f"\n⏭️  BỎ QUA (đã xử lý trước): {len(SKIPPED_FILES)} files")

print(f"\n📁 Tổng số file hợp lệ trong state: {len(PROCESSED)}")
print(f"📁 Thư mục downloads: {DOWNLOAD_DIR}")

# Thống kê theo loại
docx_count = sum(1 for v in PROCESSED.values() if v.get("type") == "docx")
pdf_count = sum(1 for v in PROCESSED.values() if v.get("type") == "pdf")

print(f"\n📊 THỐNG KÊ STATE:")
print(f"   DOCX: {docx_count}")
print(f"   PDF : {pdf_count}")

print("\n" + "=" * 70)
print("✅ VALIDATION PIPELINE HOÀN THÀNH!")
print("=" * 70)
