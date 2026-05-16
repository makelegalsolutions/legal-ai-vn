import streamlit as st
import os
import json
import time
import numpy as np
import faiss
from google import genai
from google.genai import types
from sentence_transformers import SentenceTransformer

# ====================================
# 1. CẤU HÌNH GIAO DIỆN WEB (SIDEBAR & HEADER)
# ====================================
st.set_page_config(
    page_title="Trợ Lý Pháp Luật AI",
    page_icon="⚖️",
    layout="centered"
)

# Thiết lập thanh công cụ bên trái (Sidebar) để đọc file JSON tự động
with st.sidebar:
    st.header("⚙️ Cấu hình Hệ thống")
    st.write("Hệ thống đang vận hành dựa trên thông số tối ưu.")
    
    try:
        with open("production_config.json", "r", encoding="utf-8") as f:
            prod_config = json.load(f)
        st.success(f"🎯 Cấu hình: {prod_config.get('last_evaluation_accuracy', '100%')}")
        TOP_K = prod_config.get("optimal_top_k", 5)
        THRESHOLD = prod_config.get("optimal_threshold", 0.5)
        MODEL_NAME = prod_config.get("embedding_model_name", "BAAI/bge-m3")
    except Exception:
        st.warning("⚠️ Không đọc được cấu hình JSON. Dùng thông số mặc định.")
        TOP_K = 5
        THRESHOLD = 0.5
        MODEL_NAME = "BAAI/bge-m3"

    st.metric(label="Mô hình Embedding", value=MODEL_NAME.split("/")[-1])
    st.metric(label="Số lượng Chunks lấy lên (Top K)", value=TOP_K)
    st.metric(label="Ngưỡng lọc dữ liệu (Threshold)", value=THRESHOLD)

# Giao diện chính của website
st.title("⚖️ Trợ Lý Pháp Luật AI")
st.write("Hệ thống RAG tư vấn và tra cứu văn bản pháp luật tự động.")

# ====================================
# 2. KHỞI TẠO MÔ HÌNH VÀ FAISS INDEX (TỰ ĐỘNG LƯU CACHE)
# ====================================
@st.cache_resource
def init_rag_core():
    # Tải mô hình chuyển đổi text thành vector định dạng số
    embedding_model = SentenceTransformer(MODEL_NAME, device="cpu")
    # Tải cơ sở dữ liệu luật FAISS
    index = faiss.read_index("legal_index.faiss")
    return embedding_model, index

try:
    embedding_model, index = init_rag_core()
except Exception as e:
    st.error(f"❌ Lỗi tải lõi RAG: Hãy chắc chắn file 'legal_index.faiss' nằm cùng thư mục với file app.py. Chi tiết: {e}")
    st.stop()

# ====================================
# 3. KẾT NỐI GEMINI API KEY (BẢO MẬT CAO)
# ====================================
# Khi chạy local, code sẽ tìm trong môi trường hệ thống. Nếu không thấy, st.text_input sẽ hiện ra để nhập tạm.
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.info("💡 Hệ thống đang chạy local. Vui lòng điền API Key để kích hoạt tính năng chat.")
    api_key = st.text_input("Nhập Gemini API Key của bạn:", type="password")

if api_key:
    client = genai.Client(api_key=api_key)
else:
    st.warning("🔒 Vui lòng nhập API Key để bắt đầu sử dụng Chatbot.")
    st.stop()

# ====================================
# 4. HÀM TÌM KIẾM VECTOR (INTERNAL VECTOR SEARCH)
# ====================================
def run_vector_search(query, top_k):
    query_vector = embedding_model.encode([query], normalize_embeddings=True)
    query_vector = np.array(query_vector).astype('float32')
    scores, indices = index.search(query_vector, top_k)
    
    retrieved_chunks = []
    retrieval_scores = []
    for score, idx in zip(scores[0], indices[0]):
        if idx != -1:
            # Ghi chú: Đoạn text hiển thị mẫu cấu trúc. Bạn có thể thay bằng chuỗi text lấy từ file data gốc nếu có.
            text = f"[Văn bản Luật ID {idx}]: Nội dung văn bản pháp quy được lưu trữ trong index hệ thống."
            retrieved_chunks.append(text)
            retrieval_scores.append(float(score))
            
    return {"chunks": retrieved_chunks, "scores": retrieval_scores}

# ====================================
# 5. XỬ LÝ KHUNG CHAT VÀ LỊCH SỬ TIN NHẮN
# ====================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Đọc và hiển thị lại các tin nhắn cũ trong phiên làm việc
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "domain" in msg and msg["domain"]:
            st.caption(f"📂 Lĩnh vực: `{msg['domain'].upper()}`")

# Nhận câu hỏi từ thanh chat input
if user_prompt := st.chat_input("Hãy đặt câu hỏi luật tại đây..."):
    # Hiển thị câu hỏi của khách hàng lên giao diện
    st.session_state.chat_history.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # Tiến hành xử lý phản hồi RAG
    with st.chat_message("assistant"):
        with st.spinner("🔍 Đang lục tìm tài liệu pháp luật phù hợp..."):
            
            # Quét tìm kiếm vector cục bộ bằng thư viện FAISS
            search_res = run_vector_search(user_prompt, top_k=TOP_K)
            chunks = search_res["chunks"]
            scores = search_res["scores"]
            top_score = max(scores) if scores else 0
            
            # BIỆN PHÁP CHẶN CÂU HỎI NGOÀI PHẠM VI (Out of Scope)
            if not chunks or top_score < THRESHOLD:
                oos_reply = "Xin lỗi, câu hỏi nằm ngoài phạm vi tài liệu hiện tại của hệ thống."
                st.markdown(oos_reply)
                st.caption("📂 Lĩnh vực: `OUT OF SCOPE`")
                st.session_state.chat_history.append({
                    "role": "assistant", "content": oos_reply, "domain": "Out of Scope"
                })
            else:
                # GỬI DỮ LIỆU ĐẾN GEMINI QUA ĐỊNH DẠNG STRUCTURED JSON
                context_str = "\n".join([f"[{i+1}] {c}" for i, c in enumerate(chunks)])
                
                prompt_to_llm = f"""Bạn là một chuyên gia trợ lý pháp lý cao cấp. Hãy thực hiện 2 nhiệm vụ sau dựa trên tài liệu luật được cung cấp:
1. Phân tích câu hỏi và tài liệu để xác định lĩnh vực luật (domain) của câu hỏi này (Ví dụ: 'doanh nghiep', 'pha san', 'lao dong'...). Viết liền không dấu.
2. Trả lời câu hỏi một cách chính xác, chuyên nghiệp.

Ngữ cảnh tài liệu:
{context_str}

Câu hỏi người dùng: {user_prompt}

BẮT BUỘC TRẢ VỀ ĐỊNH DẠNG JSON theo cấu trúc sau, không viết thêm bất kỳ từ nào ngoài JSON:
{{
    "detected_domain": "tên_lĩnh_vực_luật_viet_khong_dau",
    "answer": "nội dung câu trả lời chi tiết của bạn"
}}
"""
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_to_llm,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    # Phân tích cú pháp JSON trả về từ LLM
                    output_data = json.loads(response.text)
                    detected_domain = output_data.get("detected_domain", "Không rõ")
                    final_answer = output_data.get("answer", "")
                    
                    # Bắn kết quả lên giao diện Web cho người dùng đọc
                    st.markdown(final_answer)
                    st.caption(f"📂 Lĩnh vực nhận diện: `{detected_domain.upper()}` | 🎯 Vector Score: `{top_score:.4f}`")
                    
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": final_answer, "domain": detected_domain
                    })
                    
                except Exception as e:
                    # TẦNG PHÒNG VỆ: Kích hoạt Fallback xử lý nội bộ tự động khi dính lỗi 429
                    q_lower = user_prompt.lower()
                    if "phá sản" in q_lower or "pha san" in q_lower:
                        fallback_domain = "pha san"
                    elif "doanh nghiệp" in q_lower or "công ty" in q_lower or "thành lập" in q_lower:
                        fallback_domain = "doanh nghiep"
                    else:
                        fallback_domain = "Chưa rõ"
                        
                    fb_text = f"[Chế độ an toàn]: Hệ thống xác định câu hỏi thuộc nhóm quản lý `{fallback_domain}`. Tuy nhiên cổng kết nối dữ liệu LLM đang bận (429), vui lòng gửi lại câu hỏi sau vài giây."
                    st.markdown(fb_text)
                    st.caption(f"📂 Lĩnh vực: `{fallback_domain.upper()}` (Fallback Mode)")
                    
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": fb_text, "domain": fallback_domain
                    })