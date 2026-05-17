import os
import json
from pathlib import Path
from datetime import datetime

from docx import Document
from PyPDF2 import PdfReader

# ========================================
# CONFIG
# ========================================
DOWNLOAD_DIR = "data/downloads"
TEXTS_DIR = "data/texts"
STATE_FILE = "data/state/processed_files.json"

os.makedirs(TEXTS_DIR, exist_ok=True)
os.makedirs("data/logs", exist_ok=True)

# ========================================
# LOAD PROCESSED FILES FROM UPDATE STEP
# ========================================
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        PROCESSED = json.load(f)
else:
    PROCESSED = {}
    print("⚠️ Không tìm thấy file state. Vui lòng chạy update script trước.")

# ========================================
# CLEAN TEXT FUNCTION
# ========================================
def clean_text(text: str) -> str:
    if not text:
        return ""

    # Thay thế ký tự đặc biệt
    text = text.replace("\xa0", " ")
    text = text.replace("\u202f", " ")   # narrow no-break space
    text = text.replace("\u200b", "")    # zero width space

    # Giảm nhiều dòng trống xuống còn 2 dòng
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    # Giảm nhiều khoảng trắng
    while "  " in text:
        text = text.replace("  ", " ")

    # Chuẩn hóa dấu đầu dòng pháp luật (tùy chọn)
    text = text.replace("Điều ", "\nĐiều ")
    text = text.replace("Chương ", "\nChương ")

    return text.strip()


# ========================================
# TEXT EXTRACTION
# ========================================
TEXTS = []

print("🚀 Bắt đầu trích xuất văn bản từ file...")

for filename in PROCESSED.keys():
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    if not os.path.exists(filepath):
        print(f"⚠️ File không tồn tại: {filename}")
        continue

    text = ""
    
    try:
        if filename.lower().endswith(".docx"):
            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs]
            text = "\n".join(paragraphs)
            print(f"✓ DOCX: {filename}")

        elif filename.lower().endswith(".pdf"):
            reader = PdfReader(filepath)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            print(f"✓ PDF : {filename}")

        else:
            print(f"⏭️  Bỏ qua (không hỗ trợ): {filename}")
            continue

        # Clean text
        cleaned_text = clean_text(text)

        if len(cleaned_text) < 200:
            print(f"⚠️  Văn bản quá ngắn sau clean: {filename}")
            continue

        TEXTS.append({
            "source": filename,
            "text": cleaned_text,
            "processed_at": datetime.now().isoformat()
        })

    except Exception as e:
        print(f"❌ Lỗi xử lý {filename}: {e}")

# ========================================
# SAVE RESULTS
# ========================================
output_file = os.path.join(
    TEXTS_DIR, 
    f"legal_texts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
)

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(TEXTS, f, ensure_ascii=False, indent=2)

# Lưu bản latest để các bước sau dễ dùng
with open(os.path.join(TEXTS_DIR, "legal_texts_latest.json"), "w", encoding="utf-8") as f:
    json.dump(TEXTS, f, ensure_ascii=False, indent=2)

# ========================================
# SUMMARY
# ========================================
print("=" * 60)
print("✅ TEXT PROCESSING HOÀN THÀNH")
print(f"📊 Tổng số văn bản đã xử lý: {len(TEXTS)}")
print(f"📁 File output: {output_file}")
print(f"📁 Bản latest: data/texts/legal_texts_latest.json")
print("=" * 60)
