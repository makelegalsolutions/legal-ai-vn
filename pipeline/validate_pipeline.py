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

MIN_TEXT_LENGTH = 200

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

        if size < 100:

            return False, "FILE TOO SMALL"

        return True, None

    except Exception as e:

        return False, str(e)


# ========================================
# VALIDATE DOCX
# ========================================

def validate_docx(filepath):

    try:

        doc = Document(filepath)

        text = "\n".join(
            [p.text for p in doc.paragraphs]
        )

        if len(text.strip()) < MIN_TEXT_LENGTH:

            return False, "EMPTY OR TOO SHORT DOCX"

        return True, text

    except Exception as e:

        return False, str(e)


# ========================================
# VALIDATE PDF
# ========================================

def validate_pdf(filepath):

    try:

        reader = PdfReader(filepath)

        if reader.is_encrypted:

            return False, "ENCRYPTED PDF"

        text = ""

        for page in reader.pages:

            extracted = page.extract_text()

            if extracted:

                text += extracted

        if len(text.strip()) < MIN_TEXT_LENGTH:

            return False, "EMPTY PDF TEXT OR SCAN PDF"

        return True, text

    except Exception as e:

        return False, str(e)


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

query = (
    f"'{DRIVE_FOLDER_ID}' in parents "
    f"and trashed=false"
)

DRIVE_FILES = DRIVE.ListFile(
    {'q': query}
).GetList()


# ========================================
# DOWNLOAD NEW FILES
# ========================================

ALL_FILES = []

for drive_file in DRIVE_FILES:

    original_name = drive_file["title"]

    if not is_valid_extension(original_name):

        continue

    file_size = int(
        drive_file.get("fileSize", 0)
    )

    if original_name in PROCESSED:

        old_size = PROCESSED[
            original_name
        ]["size"]

        if old_size == file_size:

            SKIPPED_FILES.append(
                original_name
            )

            continue

    save_path = os.path.join(
        DOWNLOAD_DIR,
        original_name
    )

    drive_file.GetContentFile(save_path)

    ALL_FILES.append(original_name)


# ========================================
# PROCESS FILES
# ========================================

for filename in ALL_FILES:

    filepath = os.path.join(
        DOWNLOAD_DIR,
        filename
    )

    file_size = os.path.getsize(
        filepath
    )

    # =========================
    # FILE INTEGRITY CHECK
    # =========================

    ok, message = integrity_check(
        filepath
    )

    if not ok:

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

            DOCX_OK.append({
                "file": filename,
                "size": file_size
            })

            PROCESSED[filename] = {
                "size": file_size
            }

        else:

            DOCX_ERROR.append({
                "file": filename,
                "error": result
            })

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

            PDF_OK.append({
                "file": filename,
                "size": file_size
            })

            PROCESSED[filename] = {
                "size": file_size
            }

        else:

            PDF_ERROR.append({
                "file": filename,
                "error": result
            })


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

print("=" * 50)
print("VALIDATION SUMMARY")
print("=" * 50)

print(f"DOCX OK     : {len(DOCX_OK)}")
print(f"PDF OK      : {len(PDF_OK)}")

print(f"DOCX ERROR  : {len(DOCX_ERROR)}")
print(f"PDF ERROR   : {len(PDF_ERROR)}")

print(f"SKIPPED     : {len(SKIPPED_FILES)}")


# ========================================
# PRINT ERRORS
# ========================================

if DOCX_ERROR:

    print("\nDOCX ERRORS")

    for item in DOCX_ERROR:

        print(item)

if PDF_ERROR:

    print("\nPDF ERRORS")

    for item in PDF_ERROR:

        print(item)
