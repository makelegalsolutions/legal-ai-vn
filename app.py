import sys
from pathlib import Path
# Thêm ngay sau các import
import os
import json

# ==================== DEBUG: KIỂM TRA DỮ LIỆU ====================
st.sidebar.title("🔧 System Status")

# Kiểm tra thư mục data
data_paths = {
    "Chunks file": "data/chunks/legal_chunks_latest.json",
    "FAISS index": "data/vectorstore/legal_index.faiss",
    "Latest version": "data/vectorstore/latest_version.txt",
    "Processed files": "data/state/processed_files.json"
}

for name, path in data_paths.items():
    if os.path.exists(path):
        if path.endswith(".json"):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    size = len(data) if isinstance(data, list) else len(data.keys())
                st.sidebar.success(f"✅ {name}: {size} items")
            except:
                st.sidebar.success(f"✅ {name}: exists")
        else:
            size = os.path.getsize(path) / 1024 / 1024  # MB
            st.sidebar.success(f"✅ {name}: {size:.1f} MB")
    else:
        st.sidebar.error(f"❌ {name}: NOT FOUND")

# Kiểm tra version
version_file = "data/vectorstore/latest_version.txt"
if os.path.exists(version_file):
    with open(version_file, "r") as f:
        version = f.read().strip()
    st.sidebar.info(f"📌 Current version: {version}")
else:
    st.sidebar.warning("⚠️ No version file found")
# =================================================================
# ==================== FIX IMPORT CHO STREAMLIT CLOUD ====================
# Thêm đường dẫn để Python tìm được thư mục pipeline
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))
# =====================================================================

import streamlit as st
import time

# Import từ pipeline
from pipeline.config import check_api_keys, GEMINI_API_KEY

# ==================== SỬA: import có xử lý lỗi ====================
try:
    from pipeline.llm_pipeline import ask_legal_ai
except Exception as e:
    st.error(f"Lỗi khởi tạo pipeline: {str(e)}")
    st.stop()
# =====================================================================

# ========================================
# PAGE CONFIG
# ========================================
st.set_page_config(
    page_title="Legal AI VN",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý Pháp luật Việt Nam**")
    
    st.info("""
    Hệ thống sử dụng **RAG + Gemini**  
    Dựa trên văn bản pháp luật chính thức.
    """)
    
    if st.button("🔑 Kiểm tra API Key"):
        check_api_keys()
    
    st.divider()
    st.caption("Phiên bản: MVP v0.1")

# ========================================
# MAIN INTERFACE
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh dựa trên văn bản gốc")

query = st.text_area(
    "Nhập câu hỏi của bạn:",
    placeholder="Ví dụ: Nghỉ thai sản được bao nhiêu tháng? Điều kiện thành lập công ty TNHH?",
    height=130
)

col1, col2 = st.columns(2)
with col1:
    top_k = st.slider("Số văn bản tham khảo", min_value=3, max_value=10, value=6)
with col2:
    threshold = st.slider("Ngưỡng độ tin cậy", 0.30, 0.70, 0.45, step=0.01)

if st.button("🔍 Tra cứu & Trả lời", type="primary", use_container_width=True):
    if not query or not query.strip():
        st.warning("Vui lòng nhập câu hỏi!")
    elif not GEMINI_API_KEY:
        st.error("Chưa thiết lập GEMINI_API_KEY. Vui lòng kiểm tra Settings → Secrets trên Streamlit Cloud.")
    else:
        with st.spinner("Đang tra cứu văn bản pháp luật và phân tích..."):
            start = time.time()
            result = ask_legal_ai(
                query=query.strip(),
                top_k=top_k,
                threshold=threshold
            )
            latency = round(time.time() - start, 2)

        if result["status"] == "ok":
            st.success("**Câu trả lời:**")
            st.markdown(result["answer"])
            
            with st.expander("📚 Xem nguồn trích dẫn"):
                for i, chunk in enumerate(result.get("retrieved_chunks", []), 1):
                    st.markdown(f"**{i}. {chunk.get('article', 'N/A')}** — {chunk.get('title', '')[:150]}...")
                    st.caption(f"Độ tin cậy: {chunk.get('score', 0):.4f}")
                    
        elif result["status"] in ["out_of_scope", "no_result"]:
            st.warning(result.get("message", "Không tìm thấy thông tin phù hợp."))
        else:
            st.error(result.get("message", "Có lỗi xảy ra khi xử lý."))

        st.caption(f"⏱️ Thời gian xử lý: {latency} giây")

# Footer
st.divider()
st.caption("⚠️ Thông tin chỉ mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
