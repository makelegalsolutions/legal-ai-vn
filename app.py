import streamlit as st
import time
from pathlib import Path

# Import từ pipeline
from pipeline.config import check_api_keys
from pipeline.llm_pipeline import ask_legal_ai

# ========================================
# CONFIG
# ========================================
st.set_page_config(
    page_title="Legal AI VN - Trợ lý Pháp luật Việt Nam",
    page_icon="⚖️",
    layout="centered"
)

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý pháp luật Việt Nam**")
    
    st.info("Hệ thống đang sử dụng **Gemini + RAG** trên văn bản pháp luật chính thức.")
    
    if st.button("🔄 Kiểm tra API Key"):
        check_api_keys()
    
    st.caption("Phiên bản: MVP v0.1")

# ========================================
# MAIN INTERFACE
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật dựa trên văn bản gốc")

# Input
query = st.text_area(
    "Nhập câu hỏi pháp luật của bạn:",
    placeholder="Ví dụ: Nghỉ thai sản được bao nhiêu tháng? Hoặc Điều kiện thành lập công ty TNHH?",
    height=120
)

col1, col2 = st.columns([1, 1])
with col1:
    top_k = st.slider("Số lượng tài liệu tham khảo", 3, 10, 5)
with col2:
    threshold = st.slider("Ngưỡng độ tin cậy", 0.3, 0.7, 0.45, step=0.01)

if st.button("🔍 Hỏi đáp", type="primary", use_container_width=True):
    if not query.strip():
        st.warning("Vui lòng nhập câu hỏi!")
    else:
        with st.spinner("Đang tra cứu văn bản pháp luật và suy nghĩ..."):
            start_time = time.time()
            
            result = ask_legal_ai(
                query=query,
                top_k=top_k,
                threshold=threshold,
                debug=False
            )
            
            latency = round(time.time() - start_time, 2)

        # Hiển thị kết quả
        if result["status"] == "ok":
            st.success("✅ Trả lời")
            st.markdown(result["answer"])
            
            with st.expander("📑 Chi tiết trích dẫn"):
                for chunk in result.get("retrieved_chunks", [])[:5]:
                    st.markdown(f"**{chunk.get('article')}** - {chunk.get('title', '')}")
                    st.caption(f"Score: {chunk.get('score', 0):.4f}")
                    
        elif result["status"] in ["out_of_scope", "no_result"]:
            st.warning(result.get("message", "Không tìm thấy thông tin phù hợp."))
        else:
            st.error(result.get("message", "Có lỗi xảy ra."))

        st.caption(f"⏱️ Thời gian xử lý: {latency} giây")

# ========================================
# FOOTER
# ========================================
st.divider()
st.caption("⚠️ Thông tin chỉ mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức từ luật sư hoặc cơ quan nhà nước.")
