import sys
from pathlib import Path
import os
import json
from datetime import datetime
import requests
import re
import time
import traceback
from typing import List, Dict, Any

# ==================== FIX IMPORT CHO STREAMLIT CLOUD ====================
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))
# =====================================================================

import streamlit as st

# ========================================
# TIỆN ÍCH 1A: LẤY NGÀY GIỜ HÀ NỘI
# ========================================
def get_hanoi_time():
    from datetime import timezone, timedelta
    tz_hanoi = timezone(timedelta(hours=7))
    return datetime.now(tz_hanoi)

# ========================================
# TIỆN ÍCH 1B: LẤY NGÀY ÂM LỊCH
# ========================================
@st.cache_data(ttl=3600)
def get_lunar_date() -> str:
    try:
        today = datetime.now()
        can = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
        chi = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]
        
        year_can = can[(today.year - 4) % 10]
        year_chi = chi[(today.year - 4) % 12]
        
        # Ngày âm lịch ước tính
        lunar_day = ((today.day + 1) % 30) or 30
        lunar_month = today.month
        if lunar_day > 28 and today.day < 5:
            lunar_month = today.month - 1 or 12
        
        return f"Ngày {lunar_day} tháng {lunar_month} năm {year_can} {year_chi}"
    except Exception:
        today = datetime.now()
        return f"{today.day}/{today.month} (DL)"

# ========================================
# TIỆN ÍCH 1C: LẤY THÔNG TIN THỜI TIẾT
# ========================================
@st.cache_data(ttl=1800)
def get_weather(city: str) -> dict:
    cities = {
        "Hà Nội": {"lat": 21.0285, "lon": 105.8542},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967},
        "TP. HCM": {"lat": 10.8231, "lon": 106.6297}
    }
    
    if city not in cities:
        return {"temp": "N/A", "icon": "❓"}
    
    try:
        coords = cities[city]
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true&timezone=Asia/Bangkok"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            temp = data.get('current_weather', {}).get('temperature', 'N/A')
            if temp != 'N/A':
                return {"temp": f"{temp}°C", "icon": "☀️" if temp > 28 else "⛅"}
    except:
        pass
    return {"temp": "N/A", "icon": "❓"}

# ========================================
# TIỆN ÍCH 2: ĐỊNH DẠNG CĂN CỨ PHÁP LÝ
# ========================================
def format_legal_basis(chunks: List[Dict]) -> str:
    """Định dạng căn cứ pháp lý từ chunks"""
    if not chunks:
        return "*Không có trích dẫn cụ thể.*"
    
    doc_map = {}
    for chunk in chunks[:10]:
        doc_id = chunk.get('doc_id', '')
        article = chunk.get('article', '')
        
        if not doc_id:
            continue
        
        # Lấy số điều
        article_num = None
        if article:
            match = re.search(r'(\d+)', str(article))
            if match:
                article_num = match.group(1)
        
        if doc_id not in doc_map:
            doc_map[doc_id] = {"articles": set()}
        if article_num:
            doc_map[doc_id]["articles"].add(article_num)
    
    lines = []
    for doc_id, info in doc_map.items():
        doc_name = doc_id.replace("-", "/")
        articles = sorted(info["articles"], key=lambda x: int(x) if str(x).isdigit() else 0)
        if articles:
            arts_str = ", ".join(str(a) for a in articles)
            lines.append(f"• {doc_name} (Điều {arts_str})")
        else:
            lines.append(f"• {doc_name}")
    
    return "\n\n".join(lines) if lines else "*Không có trích dẫn cụ thể.*"

# ========================================
# TIỆN ÍCH 3: LƯU LỊCH SỬ
# ========================================
def save_to_history(query: str, answer_preview: str):
    if "history" not in st.session_state:
        st.session_state.history = []
    
    st.session_state.history.insert(0, {
        "query": query[:150],
        "answer_preview": answer_preview[:200],
        "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    })
    
    if len(st.session_state.history) > 30:
        st.session_state.history = st.session_state.history[:30]
    
    os.makedirs("data/state", exist_ok=True)
    try:
        with open("data/state/history.json", "w", encoding="utf-8") as f:
            json.dump(st.session_state.history, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_history():
    history_file = "data/state/history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                st.session_state.history = json.load(f)
        except:
            st.session_state.history = []
    else:
        st.session_state.history = []

def init_counter():
    counter_file = "data/state/view_count.json"
    if "view_count" not in st.session_state:
        if os.path.exists(counter_file):
            try:
                with open(counter_file, "r") as f:
                    data = json.load(f)
                    st.session_state.view_count = data.get("count", 0)
                    st.session_state.total_views = data.get("total_views", 0)
            except:
                st.session_state.view_count = 0
                st.session_state.total_views = 0
        else:
            st.session_state.view_count = 0
            st.session_state.total_views = 0
        
        st.session_state.view_count += 1
        st.session_state.total_views += 1
        
        os.makedirs("data/state", exist_ok=True)
        try:
            with open(counter_file, "w") as f:
                json.dump({"count": st.session_state.view_count, "total_views": st.session_state.total_views}, f)
        except:
            pass

# ========================================
# IMPORT PIPELINE
# ========================================
from pipeline.config import check_api_keys, GEMINI_API_KEY

try:
    from pipeline.llm_pipeline import ask_legal_ai
    PIPELINE_OK = True
except Exception as e:
    PIPELINE_OK = False
    PIPELINE_ERROR = str(e)
    print(f"Import error: {traceback.format_exc()}")

# ========================================
# PAGE CONFIG
# ========================================
st.set_page_config(
    page_title="Legal AI VN",
    page_icon="⚖️",
    layout="wide"
)

# ========================================
# CSS
# ========================================
st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 280px; max-width: 320px; }
.block-container { padding-bottom: 80px !important; }
.time-info { font-size: 0.9rem; line-height: 1.8; }
.weather-card { background-color: #f0f2f6; padding: 8px; border-radius: 8px; text-align: center; }
.weather-temp { font-size: 1.2rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ========================================
# KHỞI TẠO
# ========================================
init_counter()
load_history()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False
if "file_content" not in st.session_state:
    st.session_state.file_content = ""

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý Pháp luật Việt Nam**")
    st.divider()
    
    # Thời gian
    st.markdown("### 📅 Thông tin")
    hanoi_time = get_hanoi_time()
    
    st.markdown(f"""
    <div class="time-info">
        🕐 {hanoi_time.strftime("%H:%M:%S")}<br>
        📆 {hanoi_time.strftime("%d/%m/%Y")}<br>
        📖 {get_lunar_date()}
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    # Thời tiết
    st.markdown("### 🌡️ Thời tiết")
    cols = st.columns(3)
    for idx, city in enumerate(["Hà Nội", "Nha Trang", "TP. HCM"]):
        w = get_weather(city)
        with cols[idx]:
            st.markdown(f"""
            <div class="weather-card">
                <b>{city}</b><br>
                <span class="weather-temp">{w['temp']}</span>
            </div>
            """, unsafe_allow_html=True)
    st.divider()
    
    # Thống kê
    st.metric("👁️ Lượt xem hôm nay", st.session_state.view_count)
    st.metric("📊 Tổng lượt xem", st.session_state.total_views)
    if st.session_state.history:
        st.metric("❓ Câu hỏi", len(st.session_state.history))
    st.divider()
    
    # File upload
    uploaded_file = st.file_uploader("📎 Đính kèm file", type=["pdf", "docx", "txt"])
    if uploaded_file is not None:
        try:
            from io import BytesIO
            from PyPDF2 import PdfReader
            from docx import Document
            
            if uploaded_file.name.endswith('.txt'):
                content = uploaded_file.read().decode("utf-8")
            elif uploaded_file.name.endswith('.pdf'):
                reader = PdfReader(BytesIO(uploaded_file.read()))
                content = "".join(p.extract_text() or "" for p in reader.pages)
            else:
                doc = Document(BytesIO(uploaded_file.read()))
                content = "\n".join(p.text for p in doc.paragraphs)
            
            st.session_state.file_content = content[:5000]
            st.success(f"✅ {uploaded_file.name}")
        except Exception as e:
            st.error(f"Lỗi: {e}")
    
    if st.session_state.file_content and st.button("🗑️ Xóa file"):
        st.session_state.file_content = ""
        st.rerun()
    
    st.divider()
    
    # Lịch sử
    st.markdown("### 📜 Lịch sử")
    if st.session_state.history:
        if st.button("🗑️ Xóa lịch sử"):
            st.session_state.history = []
            st.session_state.messages = []
            st.rerun()
        for item in st.session_state.history[:5]:
            with st.expander(f"📌 {item['time'][:10]}..."):
                st.caption(item['query'][:100])
    else:
        st.info("Chưa có câu hỏi")
    
    st.divider()
    if st.button("🔑 API Key"):
        check_api_keys()
    
    st.caption("v1.0")

# ========================================
# MAIN CONTENT
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh")

# Kiểm tra pipeline
if not PIPELINE_OK:
    st.error(f"❌ Lỗi pipeline: {PIPELINE_ERROR}")
    st.code("Hãy kiểm tra file pipeline/llm_pipeline.py và secrets GEMINI_API_KEY")
    st.stop()

if not GEMINI_API_KEY:
    st.error("❌ Chưa có GEMINI_API_KEY")
    st.info("Vào Settings → Secrets → thêm GEMINI_API_KEY")
    st.stop()

# Hiển thị file đính kèm
if st.session_state.file_content:
    st.info(f"📎 Đã đính kèm file ({len(st.session_state.file_content):,} ký tự)")

# Lịch sử chat
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Chat input
query = st.chat_input("Nhập câu hỏi pháp luật...", disabled=st.session_state.is_processing)

# ========================================
# XỬ LÝ CÂU HỎI
# ========================================
if query and not st.session_state.is_processing:
    st.session_state.is_processing = True
    
    # Thêm câu hỏi
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").write(query)
    
    # Xây dựng query
    full_query = query
    if st.session_state.file_content:
        full_query = query + f"\n\n[File đính kèm]:\n{st.session_state.file_content}\n"
    
    # Gọi API
    with st.spinner("⚖️ Đang tra cứu..."):
        start = time.time()
        try:
            print(f"\n--- Processing: {query[:50]}...")
            result = ask_legal_ai(query=full_query.strip(), top_k=6, threshold=0.45)
            latency = round(time.time() - start, 2)
            print(f"Result status: {result.get('status')}")
            
            if result.get("status") == "ok":
                # Lấy answer
                answer_text = result.get("answer", "Không có nội dung trả lời")
                
                # Loại bỏ phần CĂN CỨ PHÁP LÝ nếu có
                if "CĂN CỨ PHÁP LÝ" in answer_text:
                    parts = answer_text.split("CĂN CỨ PHÁP LÝ")
                    main_answer = parts[0].strip()
                    legal_part = parts[1] if len(parts) > 1 else ""
                else:
                    main_answer = answer_text
                    legal_part = ""
                
                # Format legal basis từ chunks
                chunks = result.get("retrieved_chunks", [])
                legal_basis = format_legal_basis(chunks)
                
                # Kết hợp
                final_answer = f"**Trả lời:**\n\n{main_answer}\n\n---\n**Căn cứ pháp lý:**\n\n{legal_basis}\n\n---\n⏱️ {latency}s"
                
            elif result.get("status") == "out_of_scope":
                final_answer = f"⚠️ {result.get('message', 'Câu hỏi ngoài phạm vi hỗ trợ.')}"
            elif result.get("status") == "no_result":
                final_answer = f"⚠️ {result.get('message', 'Không tìm thấy thông tin.')}"
            else:
                final_answer = f"❌ {result.get('message', 'Lỗi không xác định')}"
                
        except Exception as e:
            error_msg = str(e)
            print(f"Error: {error_msg}")
            print(traceback.format_exc())
            final_answer = f"❌ Lỗi: {error_msg[:200]}"
        
        # Hiển thị
        st.session_state.messages.append({"role": "assistant", "content": final_answer})
        with st.chat_message("assistant"):
            st.markdown(final_answer)
        
        # Lưu lịch sử
        save_to_history(query, final_answer[:200])
        
        # Reset
        st.session_state.file_content = ""
        st.session_state.is_processing = False
        st.rerun()

# Footer
st.divider()
st.caption("⚠️ Thông tin tham khảo, không thay thế tư vấn pháp lý chính thức.")
