#!/usr/bin/env python
"""
Crawler for congbao.chinhphu.vn
Downloads new legal documents not yet in Google Drive
"""

import os
import re
import time
import json
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Set

# ========================================
# CONFIG
# ========================================
CONGBAO_URL = "https://congbao.chinhphu.vn"
LIST_URL = f"{CONGBAO_URL}/van-ban-moi"
DOWNLOAD_DIR = "data/downloads"
STATE_FILE = "data/state/processed_files.json"
LOG_DIR = "data/logs"
CRAWLED_LOG = os.path.join(LOG_DIR, "crawled_urls.json")

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Validation
MIN_FILE_SIZE = 10000  # 10KB
MIN_TEXT_LENGTH = 500   # 500 characters

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs("data/state", exist_ok=True)


# ========================================
# LOGGING
# ========================================
def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")
    
    log_file = os.path.join(LOG_DIR, f"crawler_{datetime.now().strftime('%Y%m%d')}.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {msg}\n")


# ========================================
# LOAD EXISTING FILES
# ========================================
def load_existing_files() -> Set[str]:
    """Load danh sách file đã có từ state (Google Drive + previous crawls)"""
    existing = set()
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            existing.update(state.keys())
        log(f"Loaded {len(existing)} existing files from state")
    
    # Also check downloaded files
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.pdf', '.docx')):
                existing.add(f)
    
    return existing


# ========================================
# LOAD CRAWLED URLs
# ========================================
def load_crawled_urls() -> Set[str]:
    """Load URLs đã crawl để tránh trùng lặp trong cùng phiên"""
    if os.path.exists(CRAWLED_LOG):
        with open(CRAWLED_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("urls", []))
    return set()


def save_crawled_urls(urls: Set[str]):
    """Save crawled URLs"""
    with open(CRAWLED_LOG, "w", encoding="utf-8") as f:
        json.dump({"urls": list(urls), "last_update": datetime.now().isoformat()}, f)


# ========================================
# EXTRACT DOCUMENT INFO
# ========================================
def extract_doc_info(url: str, html: str) -> Optional[Dict]:
    """Trích xuất thông tin văn bản từ trang chi tiết"""
    soup = BeautifulSoup(html, "html.parser")
    
    # Tìm số hiệu văn bản
    so_hieu = None
    so_hieu_patterns = [
        r'số[_\s]*hiệu[:\s]*([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ0-9\-]+)',
        r'Số[:\s]*([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ0-9\-]+)',
        r'([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ]+)',
        r'([\d]+[\/\-][\d]{4}[\/\-][A-ZĐÂĂÔƠƯ0-9\-]+)',
    ]
    
    for pattern in so_hieu_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            so_hieu = match.group(1).strip()
            break
    
    if not so_hieu:
        log(f"Cannot extract số hiệu from {url}", "WARNING")
        return None
    
    # Chuẩn hóa tên file
    file_name = so_hieu.replace("/", "-").replace("\\", "-") + ".pdf"
    
    # Tìm link PDF
    pdf_url = None
    
    # Method 1: Look for PDF links
    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE))
    for link in pdf_links:
        href = link.get("href", "")
        if "download" in href.lower() or "file" in href.lower() or ".pdf" in href.lower():
            if href.startswith("/"):
                pdf_url = CONGBAO_URL + href
            elif href.startswith("http"):
                pdf_url = href
            break
    
    # Method 2: Look in iframe/embed
    if not pdf_url:
        embeds = soup.find_all(["embed", "iframe"], src=re.compile(r"\.pdf", re.IGNORECASE))
        for embed in embeds:
            src = embed.get("src", "")
            if src:
                if src.startswith("/"):
                    pdf_url = CONGBAO_URL + src
                elif src.startswith("http"):
                    pdf_url = src
                break
    
    # Method 3: Look for any link containing the document number
    if not pdf_url:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if so_hieu.replace("/", "-") in href or so_hieu.replace("/", "%2F") in href:
                if href.startswith("/"):
                    pdf_url = CONGBAO_URL + href
                elif href.startswith("http"):
                    pdf_url = href
                break
    
    if not pdf_url:
        log(f"Cannot find PDF URL for {so_hieu}", "WARNING")
        return None
    
    return {
        "so_hieu": so_hieu,
        "file_name": file_name,
        "pdf_url": pdf_url,
        "page_url": url
    }


# ========================================
# DOWNLOAD AND VALIDATE PDF
# ========================================
def download_and_validate(url: str, save_path: str) -> bool:
    """Tải PDF và kiểm tra tính hợp lệ (có text thực)"""
    try:
        # Download
        response = requests.get(url, headers=HEADERS, timeout=45)
        response.raise_for_status()
        
        # Check size
        content_length = len(response.content)
        if content_length < MIN_FILE_SIZE:
            log(f"File too small: {content_length} bytes", "WARNING")
            return False
        
        # Save
        with open(save_path, "wb") as f:
            f.write(response.content)
        
        # Validate PDF content
        from PyPDF2 import PdfReader
        
        reader = PdfReader(save_path)
        
        if reader.is_encrypted:
            log(f"Encrypted PDF", "WARNING")
            os.remove(save_path)
            return False
        
        # Extract and check text
        text = ""
        for page in reader.pages[:15]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        if len(text.strip()) < MIN_TEXT_LENGTH:
            log(f"Insufficient text: {len(text)} chars", "WARNING")
            os.remove(save_path)
            return False
        
        log(f"✅ Valid PDF: {len(text)} chars, {content_length} bytes")
        return True
        
    except Exception as e:
        log(f"Download/validation error: {e}", "ERROR")
        if os.path.exists(save_path):
            os.remove(save_path)
        return False


# ========================================
# CRAWL CONGBAO
# ========================================
def crawl_congbao(max_pages: int = 10, max_per_page: int = 30) -> List[Dict]:
    """Crawl danh sách văn bản mới"""
    
    existing_files = load_existing_files()
    crawled_urls = load_crawled_urls()
    
    log(f"Existing files: {len(existing_files)}")
    log(f"Crawled URLs in this session: {len(crawled_urls)}")
    log(f"Crawling up to {max_pages} pages, {max_per_page} per page")
    
    new_docs = []
    
    for page in range(1, max_pages + 1):
        page_url = f"{LIST_URL}?page={page}"
        log(f"Crawling page {page}: {page_url}")
        
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            log(f"Failed to fetch page {page}: {e}", "ERROR")
            continue
        
        # Find document links
        doc_links = []
        
        # Try different selectors
        selectors = [
            "a.vanban-title",
            "h3 a",
            ".title a",
            "a[href*='/chi-tiet-van-ban/']",
            ".news-item a",
            ".item a"
        ]
        
        for selector in selectors:
            doc_links = soup.select(selector)
            if doc_links:
                log(f"Found {len(doc_links)} links using selector: {selector}")
                break
        
        if not doc_links:
            doc_links = soup.find_all("a", href=re.compile(r"/chi-tiet-van-ban/"))
            log(f"Found {len(doc_links)} links using regex")
        
        if not doc_links:
            log(f"No document links found on page {page}", "WARNING")
            continue
        
        page_new_count = 0
        
        for link in doc_links[:max_per_page]:
            href = link.get("href", "")
            if not href:
                continue
            
            # Build full URL
            if href.startswith("/"):
                full_url = CONGBAO_URL + href
            elif href.startswith("http"):
                full_url = href
            else:
                continue
            
            # Check if already crawled
            if full_url in crawled_urls:
                continue
            
            crawled_urls.add(full_url)
            
            # Fetch detail page
            try:
                time.sleep(0.5)  # Be polite
                detail_response = requests.get(full_url, headers=HEADERS, timeout=30)
                detail_response.raise_for_status()
            except Exception as e:
                log(f"Failed to fetch detail: {full_url[:80]}... - {e}", "WARNING")
                continue
            
            # Extract document info
            doc_info = extract_doc_info(full_url, detail_response.text)
            
            if not doc_info:
                continue
            
            # Check if already exists
            if doc_info["file_name"] in existing_files:
                log(f"Already exists: {doc_info['file_name']}")
                continue
            
            # Download and validate
            save_path = os.path.join(DOWNLOAD_DIR, doc_info["file_name"])
            log(f"Downloading: {doc_info['file_name']}")
            
            if download_and_validate(doc_info["pdf_url"], save_path):
                log(f"✅ New valid document: {doc_info['file_name']}")
                new_docs.append(doc_info)
                page_new_count += 1
                existing_files.add(doc_info["file_name"])
            else:
                log(f"❌ Invalid document: {doc_info['file_name']}")
            
            time.sleep(1)  # Delay between downloads
        
        log(f"Page {page}: found {page_new_count} new valid documents")
        
        # If no new docs found for 2 consecutive pages, stop
        if page_new_count == 0 and page > 2:
            log("No new documents found in last 2 pages, stopping crawl")
            break
        
        time.sleep(2)  # Delay between pages
    
    # Save crawled URLs
    save_crawled_urls(crawled_urls)
    
    return new_docs


# ========================================
# UPDATE STATE WITH NEW DOCS
# ========================================
def update_state(new_docs: List[Dict]):
    """Update state file with newly downloaded documents"""
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
                "crawled_at": datetime.now().isoformat(),
                "type": "pdf"
            }
    
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ========================================
# MAIN
# ========================================
def main():
    print("=" * 70)
    print("🕷️  CRAWLER: CONGBAO.CHINHPHU.VN")
    print("=" * 70)
    
    # Get max pages from environment or default
    max_pages = int(os.environ.get("MAX_CRAWL_PAGES", 5))
    
    new_docs = crawl_congbao(max_pages=max_pages, max_per_page=20)
    
    if new_docs:
        update_state(new_docs)
        print("\n" + "=" * 70)
        print(f"✅ SUCCESS: Downloaded {len(new_docs)} new documents")
        print("=" * 70)
        for doc in new_docs:
            print(f"   📄 {doc['file_name']}")
            print(f"      URL: {doc['page_url']}")
        print("=" * 70)
    else:
        print("\n📭 No new documents found")
    
    # Summary
    log(f"CRAWL SUMMARY: {len(new_docs)} new documents")
    
    # Output for GitHub Actions
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"new_docs={len(new_docs)}\n")


if __name__ == "__main__":
    main()
