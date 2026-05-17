import sys
from pathlib import Path
import os
import json
from datetime import datetime
import requests
import re
import time
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
# TIỆN ÍCH 1B: LẤY NGÀY ÂM LỊCH CHÍNH XÁC
# ========================================
@st.cache_data(ttl=3600)
def get_lunar_date():
    """Lấy ngày âm lịch chính xác từ API"""
    try:
        today = datetime.now()
        url = f"https://lunar.dragon-style.com/api/v1/lunar?date={today.day}/{today.month}/{today.year}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            lunar_day = data.get('lunar_day', '')
            lunar_month = data.get('lunar_month', '')
            lunar_year = data.get('lunar_year', '')
            if lunar_day and lunar_month and lunar_year:
                return f"Ngày {lunar_day} tháng {lunar_month} năm {lunar_year}"
    except:
        pass
    
    # Fallback
    today = datetime.now()
    return f"Đang cập nhật (ngày {today.day}/{today.month})"

# ========================================
# TIỆN ÍCH 1C: LẤY THÔNG TIN THỜI TIẾT
# ========================================
@st.cache_data(ttl=1800)
def get_weather_detailed(city: str) -> dict:
    cities = {
        "Hà Nội": {"lat": 21.0285, "lon": 105.8542},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967},
        "TP. HCM": {"lat": 10.8231, "lon": 106.6297}
    }
    
    if city not in cities:
        return {"temp": "N/A", "condition": "N/A", "icon": "❓"}
    
    try:
        coords = cities[city]
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true&timezone=Asia/Bangkok"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            temp = current.get('temperature', 'N/A')
            
            if temp == 'N/A':
                condition = "N/A"
                icon = "❓"
            elif temp > 35:
                condition = "Nắng nóng gay gắt"
                icon = "🥵☀️"
            elif temp > 32:
                condition = "Nắng nóng"
                icon = "☀️🔥"
            elif temp > 28:
                condition = "Nắng"
                icon = "☀️"
            elif temp > 24:
                condition = "Mát mẻ"
                icon = "⛅"
            elif temp > 20:
                condition = "Se lạnh"
                icon = "🌥️"
            else:
                condition = "Lạnh"
                icon = "☁️"
            
            return {
                "temp": f"{temp}°C",
                "condition": condition,
                "icon": icon
            }
    except:
        pass
    
    return {"temp": "N/A", "condition": "N/A", "icon": "❓"}

# ========================================
# TIỆN ÍCH 2: XỬ LÝ VĂN BẢN VÀ TRÍCH DẪN
# ========================================
def extract_doc_type(doc_id: str) -> str:
    """Trích xuất loại văn bản từ số hiệu"""
    if not doc_id:
        return "Văn bản"
    doc_id_upper = doc_id.upper()
    if "LUAT" in doc_id_upper or ("QH" in doc_id_upper and len(doc_id_upper) < 20):
        return "Luật"
    elif "ND-CP" in doc_id_upper or "ND" in doc_id_upper:
        return "Nghị định"
    elif "TT" in doc_id_upper:
        return "Thông tư"
    elif "QD" in doc_id_upper:
        return "Quyết định"
    elif "NQ" in doc_id_upper:
        return "Nghị quyết"
    elif "PL" in doc_id_upper:
        return "Pháp lệnh"
    else:
        return "Văn bản"

def format_doc_name(doc_id: str) -> str:
    """Định dạng tên văn bản: Luật 60/2024/QH15"""
    if not doc_id:
        return ""
    doc_type = extract_doc_type(doc_id)
    formatted_id = doc_id.replace("-", "/")
    return f"{doc_type} {formatted_id}"

def extract_articles_from_chunks(chunks: List[Dict]) -> Dict[str, Dict]:
    """Trích xuất các Điều từ chunks, nhóm theo văn bản"""
    doc_articles = {}
    
    if not chunks:
        return doc_articles
    
    for chunk in chunks:
        doc_id = chunk.get('doc_id', '')
        article = chunk.get('article', '')
        title = chunk.get('title', '')
        
        if not doc_id:
            continue
        
        # Trích xuất số Điều
        article_num = None
        if article:
            article_match = re.search(r'Điều\s+(\d+)', str(article), re.IGNORECASE)
            if article_match:
                article_num = int(article_match.group(1))
        
        if doc_id not in doc_articles:
            doc_articles[doc_id] = {
                "title": title,
                "articles": set()
            }
        
        if article_num:
            doc_articles[doc_id]["articles"].add(article_num)
    
    # Sắp xếp các Điều tăng dần và chuyển set thành list
    for doc_id in doc_articles:
        doc_articles[doc_id]["articles"] = sorted(doc_articles[doc_id]["articles"])
    
    return doc_articles

def format_legal_basis(doc_articles: Dict[str, Dict]) -> str:
    """Định dạng căn cứ pháp lý từ các văn bản và điều khoản"""
    if not doc_articles:
        return "*Không có trích dẫn cụ thể từ văn bản pháp luật.*"
    
    lines = []
    for doc_id, info in doc_articles.items():
        doc_name = format_doc_name(doc_id)
        title = info.get('title', '')
        
        # Tạo chuỗi văn bản
        if title and title != doc_id:
            doc_line = f"**{doc_name}** - {title}"
        else:
            doc_line = f"**{doc_name}**"
        
        # Thêm các Điều
        articles = info.get("articles", [])
        if articles:
            if len(articles) == 1:
                doc_line += f", Điều {articles[0]}"
            else:
                articles_str = ", ".join([str(a) for a in articles])
                doc_line += f", các Điều {articles_str}"
        
        lines.append(doc_line)
    
    return "\n\n".join(lines)

# ========================================
# TIỆN ÍCH 3: PHÁT HIỆN NGÔN NGỮ
# ========================================
def detect_language(text: str) -> str:
    """Phát hiện ngôn ngữ của câu hỏi"""
    if not text:
        return "vi"
    
    # Kiểm tra ký tự tiếng Việt có dấu
    vietnamese_chars = r'[ăâđêôơưàáảãạâầấẩẫậăằắẳẵặêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]'
    if re.search(vietnamese_chars, text, re.IGNORECASE):
        return "vi"
    
    # Kiểm tra ký tự Hán (tiếng Trung)
    chinese_chars = r'[\u4e00-\u9fff]'
    if re.search(chinese_chars, text):
        return "zh"
    
    # Kiểm tra ký tự Hangul (tiếng Hàn)
    korean_chars = r'[\uac00-\ud7af]'
    if re.search(korean_chars, text):
        return "ko"
    
    # Kiểm tra ký tự Katakana/Hiragana (tiếng Nhật)
    japanese_chars = r'[\u3040-\u309f\u30a0-\u30ff]'
    if re.search(japanese_chars, text):
        return "ja"
    
    # Mặc định là tiếng Việt
    return "vi"

# ========================================
# TIỆN ÍCH 4: LƯU LỊCH SỬ
# ========================================
def save_to_history(query: str, answer_preview: str):
    if "history" not in st.session_state:
        st.session_state.history = []
    
    new_item = {
        "query": query[:150],
        "answer_preview": answer_preview[:200],
        "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
        "timestamp": datetime.now().timestamp()
    }
    st.session_state.history.insert(0, new_item)
    
    if len(st.session_state.history) > 30:
        st.session_state.history = st.session_state.history[:30]
    
    os.makedirs("data/state", exist_ok=True)
    try:
        with open("data/state/history.json", "w", encoding="utf-8") as f:
            json.dump(st.session_state.history, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_history_from_file():
    history_file = "data/state/history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                st.session_state.history = json.load(f)
        except:
            st.session_state.history = []
    else:
        st.session_state.history = []

def init_view_counter():
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
                json.dump({
                    "count": st.session_state.view_count,
                    "total_views": st.session_state.total_views,
                    "last_updated": datetime.now().isoformat()
                }, f)
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

# ========================================
# PAGE CONFIG
# ========================================
st.set_page_config(
    page_title="Legal AI VN - Trợ lý Pháp luật Việt Nam",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================
# CSS
# ========================================
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        min-width: 320px;
        max-width: 380px;
    }
    
    .time-info {
        font-size: 1rem;
        line-height: 1.8;
        margin-bottom: 10px;
    }
    
    .weather-card {
        background-color: #f0f2f6;
        padding: 10px 5px;
        border-radius: 10px;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .weather-temp {
        font-size: 1.3rem;
        font-weight: bold;
        color: #1e1e1e;
    }
    .weather-condition {
        font-size: 0.8rem;
        color: #333333;
        margin-top: 4px;
    }
    
    /* Ẩn file uploader mặc định */
    .stFileUploader > div:first-child {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# ========================================
# KHỞI TẠO
# ========================================
init_view_counter()
load_history_from_file()

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
    st.markdown("### 📅 Thông tin thời gian")
    hanoi_time = get_hanoi_time()
    lunar_date = get_lunar_date()
    
    st.markdown(f"""
    <div class="time-info">
        <b>🕐 Giờ Hà Nội:</b> <span style="font-size: 1.1rem;">{hanoi_time.strftime("%H:%M:%S")}</span><br>
        <b>📆 Dương lịch:</b> <span style="font-size: 1rem;">{hanoi_time.strftime("%d/%m/%Y")}</span><br>
        <b>📖 Âm lịch:</b> <span style="font-size: 1rem;">{lunar_date}</span>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    # Thời tiết
    st.markdown("### 🌡️ Thời tiết hôm nay")
    cities = ["Hà Nội", "Nha Trang", "TP. HCM"]
    cols = st.columns(3)
    
    for idx, city in enumerate(cities):
        w = get_weather_detailed(city)
        with cols[idx]:
            st.markdown(f"""
            <div class="weather-card">
                <div><b>{w['icon']} {city}</b></div>
                <div class="weather-temp">{w['temp']}</div>
                <div class="weather-condition">{w['condition']}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    # Thống kê
    st.markdown("### 📊 Thống kê")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("👁️ Lượt xem hôm nay", f"{st.session_state.view_count:,}")
    with col2:
        st.metric("📊 Tổng lượt xem", f"{st.session_state.total_views:,}")
    
    if "history" in st.session_state:
        st.metric("❓ Câu hỏi đã hỏi", len(st.session_state.history))
    st.divider()
    
    # Lịch sử
    st.markdown("### 📜 Lịch sử câu hỏi")
    if "history" in st.session_state and st.session_state.history:
        if st.button("🗑️ Xóa lịch sử", key="clear_history", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        
        for i, item in enumerate(st.session_state.history[:10]):
            with st.expander(f"📌 {item['time'][:10]}..."):
                st.caption(f"**Câu hỏi:** {item['query']}")
                st.caption(f"**Trả lời:** {item['answer_preview']}...")
    else:
        st.info("💬 Chưa có câu hỏi nào")
    st.divider()
    
    # Kiểm tra hệ thống
    if st.button("🔑 Kiểm tra API Key", use_container_width=True):
        if GEMINI_API_KEY:
            st.success("✅ API Key đã cấu hình")
        else:
            st.error("❌ Chưa có API Key")
    
    st.caption("⚖️ Legal AI VN v1.0")

# ========================================
# MAIN CONTENT
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh dựa trên văn bản gốc")

# Kiểm tra pipeline
if not PIPELINE_OK:
    st.error(f"❌ Lỗi khởi tạo pipeline: {PIPELINE_ERROR}")
    st.stop()

if not GEMINI_API_KEY:
    st.error("❌ Chưa thiết lập GEMINI_API_KEY. Vui lòng kiểm tra Settings → Secrets trên Streamlit Cloud.")
    st.stop()

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.markdown(msg["content"])

# ========================================
# FILE ATTACH (trong sidebar của chat)
# ========================================
with st.sidebar:
    with st.expander("📎 Đính kèm file (PDF, DOCX, TXT)", expanded=False):
        uploaded_file = st.file_uploader(
            "Chọn file",
            type=["pdf", "docx", "txt"],
            label_visibility="collapsed"
        )
        if uploaded_file is not None:
            try:
                from io import BytesIO
                from PyPDF2 import PdfReader
                from docx import Document
                
                if uploaded_file.name.endswith('.txt'):
                    file_content = uploaded_file.read().decode("utf-8")
                elif uploaded_file.name.endswith('.pdf'):
                    reader = PdfReader(BytesIO(uploaded_file.read()))
                    file_content = ""
                    for page in reader.pages:
                        file_content += page.extract_text() or ""
                else:
                    doc = Document(BytesIO(uploaded_file.read()))
                    file_content = "\n".join([p.text for p in doc.paragraphs])
                
                st.session_state.file_content = file_content[:5000]
                st.success(f"✅ Đã tải: {uploaded_file.name} ({len(file_content)} ký tự)")
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

# ========================================
# CHAT INPUT
# ========================================
query = st.chat_input("Nhập câu hỏi pháp luật của bạn...", disabled=st.session_state.is_processing)

# Hiển thị thông báo nếu có file đính kèm
if st.session_state.file_content:
    st.info(f"📎 Đã đính kèm file ({len(st.session_state.file_content):,} ký tự)")

# ========================================
# XỬ LÝ CÂU HỎI
# ========================================
if query and not st.session_state.is_processing:
    st.session_state.is_processing = True
    
    # Thêm câu hỏi vào lịch sử
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").write(query)
    
    # Kết hợp file content
    full_query = query
    if st.session_state.file_content:
        full_query = query + f"\n\n[Nội dung file đính kèm]:\n{st.session_state.file_content}\n"
    
    # Phát hiện ngôn ngữ
    detected_lang = detect_language(query)
    lang_name = {"vi": "Tiếng Việt", "en": "English", "zh": "中文", "ko": "한국어", "ja": "日本語"}.get(detected_lang, "Tiếng Việt")
    
    # Thêm yêu cầu ngôn ngữ vào câu hỏi
    if detected_lang == "en":
        full_query = full_query + "\n\nPlease answer in English."
    elif detected_lang == "zh":
        full_query = full_query + "\n\n请用中文回答。"
    elif detected_lang == "ko":
        full_query = full_query + "\n\n한국어로 답변해주세요."
    elif detected_lang == "ja":
        full_query = full_query + "\n\n日本語で答えてください。"
    else:
        full_query = full_query + "\n\nHãy trả lời bằng tiếng Việt."
    
    # Gọi API
    with st.spinner(f"⚖️ Đang tra cứu văn bản pháp luật... (Ngôn ngữ: {lang_name})"):
        start_time = time.time()
        try:
            result = ask_legal_ai(query=full_query.strip(), top_k=8, threshold=0.45)
            latency = round(time.time() - start_time, 2)
            
            if result["status"] == "ok":
                # Lấy chunks
                retrieved_chunks = result.get("retrieved_chunks", [])
                
                # Xử lý căn cứ pháp lý
                try:
                    doc_articles = extract_articles_from_chunks(retrieved_chunks)
                    legal_basis = format_legal_basis(doc_articles)
                except Exception as e:
                    print(f"Error formatting legal basis: {e}")
                    legal_basis = "*Đang cập nhật căn cứ pháp lý...*"
                
                # Lấy phần trả lời chính
                answer_text = result.get("answer", "")
                if "CĂN CỨ PHÁP LÝ" in answer_text:
                    parts = answer_text.split("CĂN CỨ PHÁP LÝ")
                    main_answer = parts[0].strip()
                else:
                    main_answer = answer_text
                
                if not main_answer:
                    main_answer = answer_text
                
                # Xây dựng response
                final_response = f"""**Trả lời:**

{main_answer}

---
**Căn cứ pháp lý:**

{legal_basis}

---
⏱️ Thời gian xử lý: {latency} giây | 🌐 Ngôn ngữ: {lang_name}"""
                
                save_to_history(query, final_response[:200])
                
            elif result["status"] in ["out_of_scope", "no_result"]:
                final_response = f"⚠️ {result.get('message', 'Không tìm thấy thông tin phù hợp.')}\n\n💡 Gợi ý: Hãy thử hỏi về các lĩnh vực như doanh nghiệp, lao động, hành chính..."
            else:
                final_response = f"❌ {result.get('message', 'Có lỗi xảy ra khi xử lý.')}"
                
        except Exception as e:
            final_response = f"❌ Lỗi: {str(e)}"
            print(f"Error: {e}")
        
        # Hiển thị response
        st.session_state.messages.append({"role": "assistant", "content": final_response})
        with st.chat_message("assistant"):
            st.markdown(final_response)
        
        # Reset file content
        st.session_state.file_content = ""
    
    st.session_state.is_processing = False
    st.rerun()

# ========================================
# STOP BUTTON
# ========================================
if st.session_state.is_processing:
    if st.button("⏹️ Dừng tạo câu trả lời"):
        st.session_state.is_processing = False
        st.rerun()

# Footer
st.divider()
st.caption("⚠️ Thông tin mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
