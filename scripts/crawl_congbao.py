import os
import re
import time
import json
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

# ========================================
# CONFIG
# ========================================
CONGBAO_URL = "https://congbao.chinhphu.vn"
LIST_URL = f"{CONGBAO_URL}/van-ban-moi"
DOWNLOAD_DIR = "data/downloads"
STATE_FILE = "data/state/processed_files.json"
LOG_FILE = "data/logs/crawler.log"

# Headers để tránh bị chặn
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs("data/logs", exist_ok=True)
os.makedirs("data/state", exist_ok=True)

# ========================================
# LOGGING
# ========================================
def log_message(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    print(log_entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

# ========================================
# LOAD EXISTING FILES (từ Google Drive)
# ========================================
def load_existing_files():
    """Đọc danh sách file đã có từ state file (Google Drive)"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            return set(state.keys())
    return set()

# ========================================
# EXTRACT DOCUMENT INFO FROM CONGBAO
# ========================================
def extract_doc_info(url: str, html: str) -> Optional[Dict]:
    """Trích xuất thông tin văn bản từ trang chi tiết"""
    soup = BeautifulSoup(html, "html.parser")
    
    # Tìm số hiệu văn bản (ví dụ: 10/2006/ND-CP)
    so_hieu = None
    so_hieu_patterns = [
        r'số hiệu[:\s]*([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ0-9\-]+)',
        r'Số[:\s]*([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ0-9\-]+)',
        r'([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ]+)',
    ]
    
    for pattern in so_hieu_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            so_hieu = match.group(1).strip()
            break
    
    if not so_hieu:
        return None
    
    # Chuẩn hóa tên file
    file_name = so_hieu.replace("/", "-") + ".pdf"
    
    # Tìm link tải PDF
    pdf_url = None
    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE))
    for link in pdf_links:
        href = link.get("href", "")
        if "download" in href.lower() or "file" in href.lower() or ".pdf" in href.lower():
            if href.startswith("/"):
                pdf_url = CONGBAO_URL + href
            elif href.startswith("http"):
                pdf_url = href
            break
    
    if not pdf_url:
        # Thử tìm trong các iframe hoặc embed
        embeds = soup.find_all(["embed", "iframe"], src=re.compile(r"\.pdf", re.IGNORECASE))
        for embed in embeds:
            src = embed.get("src", "")
            if src:
                if src.startswith("/"):
                    pdf_url = CONGBAO_URL + src
                elif src.startswith("http"):
                    pdf_url = src
                break
    
    if not pdf_url:
        return None
    
    return {
        "so_hieu": so_hieu,
        "file_name": file_name,
        "pdf_url": pdf_url,
        "page_url": url
    }

# ========================================
# DOWNLOAD PDF
# ========================================
def download_pdf(url: str, save_path: str) -> bool:
    """Tải file PDF và kiểm tra tính hợp lệ"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Kiểm tra content-type
        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and len(response.content) < 1000:
            log_message(f"⚠️  Not PDF: {content_type}")
            return False
        
        # Kiểm tra kích thước (PDF thường > 10KB)
        if len(response.content) < 10000:
            log_message(f"⚠️  File too small: {len(response.content)} bytes")
            return False
        
        with open(save_path, "wb") as f:
            f.write(response.content)
        
        return True
    except Exception as e:
        log_message(f"❌ Download error {url}: {e}")
        return False

# ========================================
# VALIDATE PDF CONTENT (text extraction)
# ========================================
def validate_pdf_text(filepath: str, min_text_length: int = 500) -> bool:
    """Kiểm tra PDF có text thực (không phải scan)"""
    try:
        from PyPDF2 import PdfReader
        
        reader = PdfReader(filepath)
        
        if reader.is_encrypted:
            log_message(f"⚠️  Encrypted PDF: {filepath}")
            return False
        
        text = ""
        for page in reader.pages[:10]:  # Chỉ check 10 trang đầu
            page_text = page.extract_text()
            if page_text:
                text += page_text
        
        if len(text.strip()) < min_text_length:
            log_message(f"⚠️  Insufficient text: {len(text)} chars")
            return False
        
        return True
    except Exception as e:
        log_message(f"❌ Validation error: {e}")
        return False

# ========================================
# CRAWL VAN BAN MOI
# ========================================
def crawl_congbao(max_pages: int = 5, max_docs_per_page: int = 20) -> List[Dict]:
    """Crawl danh sách văn bản mới từ congbao.chinhphu.vn"""
    
    existing_files = load_existing_files()
    log_message(f"📁 Existing files: {len(existing_files)}")
    
    new_docs = []
    
    for page in range(1, max_pages + 1):
        page_url = f"{LIST_URL}?page={page}"
        log_message(f"🔍 Crawling page {page}: {page_url}")
        
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            log_message(f"❌ Failed to fetch page {page}: {e}")
            continue
        
        # Tìm các link đến văn bản
        doc_links = []
        
        # Thử các selector khác nhau
        for selector in ["a.vanban-title", "h3 a", ".title a", "a[href*='/chi-tiet-van-ban/']"]:
            doc_links = soup.select(selector)
            if doc_links:
                break
        
        if not doc_links:
            doc_links = soup.find_all("a", href=re.compile(r"/chi-tiet-van-ban/"))
        
        count = 0
        for link in doc_links[:max_docs_per_page]:
            href = link.get("href", "")
            if not href:
                continue
            
            if href.startswith("/"):
                full_url = CONGBAO_URL + href
            elif href.startswith("http"):
                full_url = href
            else:
                continue
            
            # Lấy nội dung trang chi tiết
            try:
                detail_response = requests.get(full_url, headers=HEADERS, timeout=30)
                detail_response.raise_for_status()
            except Exception as e:
                log_message(f"⚠️  Failed to fetch detail: {full_url} - {e}")
                continue
            
            doc_info = extract_doc_info(full_url, detail_response.text)
            
            if not doc_info:
                continue
            
            # Kiểm tra trùng với file đã có
            if doc_info["file_name"] in existing_files:
                log_message(f"⏭️  Already exists: {doc_info['file_name']}")
                continue
            
            # Tải PDF
            save_path = os.path.join(DOWNLOAD_DIR, doc_info["file_name"])
            log_message(f"📥 Downloading: {doc_info['file_name']}")
            
            if download_pdf(doc_info["pdf_url"], save_path):
                # Validate nội dung
                if validate_pdf_text(save_path):
                    log_message(f"✅ Valid: {doc_info['file_name']}")
                    new_docs.append(doc_info)
                    count += 1
                else:
                    log_message(f"❌ Invalid (no text): {doc_info['file_name']}")
                    os.remove(save_path)
            else:
                log_message(f"❌ Download failed: {doc_info['file_name']}")
            
            # Delay để tránh bị chặn
            time.sleep(1)
        
        log_message(f"📊 Page {page}: found {count} new valid documents")
        
        if count == 0 and page > 1:
            # Không còn văn bản mới
            break
        
        time.sleep(2)
    
    return new_docs

# ========================================
# UPDATE STATE FILE
# ========================================
def update_state(new_docs: List[Dict]):
    """Cập nhật state file với các file mới"""
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    
    for doc in new_docs:
        filepath = os.path.join(DOWNLOAD_DIR, doc["file_name"])
        if os.path.exists(filepath):
            state[doc["file_name"]] = {
                "size": os.path.getsize(filepath),
                "source": "congbao",
                "so_hieu": doc["so_hieu"],
                "crawled_at": datetime.now().isoformat()
            }
    
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ========================================
# MAIN
# ========================================
if __name__ == "__main__":
    print("=" * 70)
    print("🕷️  CRAWLER: CONGBAO.CHINHPHU.VN")
    print("=" * 70)
    
    new_docs = crawl_congbao(max_pages=5, max_docs_per_page=20)
    
    if new_docs:
        update_state(new_docs)
        print("\n" + "=" * 70)
        print(f"✅ Đã tải {len(new_docs)} văn bản mới:")
        for doc in new_docs:
            print(f"   • {doc['file_name']}")
        print("=" * 70)
    else:
        print("\n📭 Không có văn bản mới nào được tải.")
    
    # Ghi log tổng kết
    log_message(f"SUMMARY: {len(new_docs)} new documents crawled")
