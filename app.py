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
# TIỆN ÍCH 1B: LẤY NGÀY ÂM LỊCH (OFFLINE, KHÔNG CẦN API)
# ========================================
# Dùng thuật toán âm lịch đơn giản, không cần thư viện ngoài
@st.cache_data(ttl=3600)
def get_lunar_date() -> str:
    """Tính ngày âm lịch (ước tính) - không phụ thuộc API"""
    try:
        today = datetime.now()
        
        # Can chi cho năm
        can = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
        chi = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]
        
        year_can = can[(today.year - 4) % 10]
        year_chi = chi[(today.year - 4) % 12]
        
        # Tính ngày âm lịch ước tính (đơn giản)
        # Có thể thay bằng API chính xác hơn nếu cần
        lunar_day = (today.day + 1) % 30
        if lunar_day == 0:
            lunar_day = 30
        lunar_month = today.month
        if lunar_day > 28 and today.day < 5:
            lunar_month = today.month - 1
            if lunar_month == 0:
                lunar_month = 12
        
        return f"Ngày {lunar_day} tháng {lunar_month} năm {year_can} {year_chi}"
    except Exception:
        today = datetime.now()
        return f"Ngày {today.day}/{today.month} (DL)"

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
                condition, icon = "N/A", "❓"
            elif temp > 35:
                condition, icon = "Nắng nóng gay gắt", "🥵☀️"
            elif temp > 32:
                condition, icon = "Nắng nóng", "☀️🔥"
            elif temp > 28:
                condition, icon = "Nắng", "☀️"
            elif temp > 24:
                condition, icon = "Mát mẻ", "⛅"
            elif temp > 20:
                condition, icon = "Se lạnh", "🌥️"
            else:
                condition, icon = "Lạnh", "☁️"

            return {"temp": f"{temp}°C", "condition": condition, "icon": icon}
    except Exception:
        pass

    return {"temp": "N/A", "condition": "N/A", "icon": "❓"}

# ========================================
# TIỆN ÍCH 2: XỬ LÝ VĂN BẢN VÀ TRÍCH DẪN
# ========================================
_DOC_TYPE_RULES = [
    (r"LUAT|(?<!\w)QH\d{2}", "Luật"),
    (r"ND-CP|NĐ-CP", "Nghị định"),
    (r"TT-BTC|TT-", "Thông tư"),
    (r"TTLT-", "Thông tư liên tịch"),
    (r"QD-TTg|QĐ-", "Quyết định"),
    (r"NQ-", "Nghị quyết"),
    (r"CT-", "Chỉ thị"),
    (r"PL-", "Pháp lệnh"),
]

def extract_doc_type(doc_id: str) -> str:
    if not doc_id:
        return "Văn bản"
    upper = doc_id.upper()
    for pattern, label in _DOC_TYPE_RULES:
        if re.search(pattern, upper):
            return label
    return "Văn bản"

def format_doc_name(doc_id: str) -> str:
    if not doc_id:
        return ""
    doc_type = extract_doc_type(doc_id)
    formatted_id = doc_id.replace("-", "/")
    return f"{doc_type} {formatted_id}"

def extract_articles_from_chunks(chunks: List[Dict]) -> Dict[str, Dict]:
    """Trích xuất Điều từ chunks, nhóm theo văn bản"""
    doc_articles: Dict[str, Dict] = {}

    if not chunks:
        return doc_articles

    for chunk in chunks:
        doc_id = chunk.get('doc_id', '').strip()
        article = chunk.get('article', '')
        title = chunk.get('title', '')

        if not doc_id:
            continue

        article_num = None
        if article:
            m = re.search(r'Điều\s+(\d+)', str(article), re.IGNORECASE)
            if m:
                article_num = int(m.group(1))

        if doc_id not in doc_articles:
            doc_articles[doc_id] = {
                "title": title,
                "articles": set()
            }
        elif title and not doc_articles[doc_id]["title"]:
            doc_articles[doc_id]["title"] = title

        if article_num is not None:
            doc_articles[doc_id]["articles"].add(article_num)

    for doc_id in doc_articles:
        doc_articles[doc_id]["articles"] = sorted(doc_articles[doc_id]["articles"])

    return doc_articles

def format_legal_basis(doc_articles: Dict[str, Dict]) -> str:
    """Định dạng căn cứ pháp lý"""
    if not doc_articles:
        return "*Không có trích dẫn cụ thể từ văn bản pháp luật.*"

    lines = []
    for doc_id, info in doc_articles.items():
        doc_name = format_doc_name(doc_id)
        title = info.get('title', '').strip()

        if title and title != doc_id:
            line = f"**{doc_name}** — {title}"
        else:
            line = f"**{doc_name}**"

        articles = info.get("articles", [])
        if articles:
            arts_str = ", ".join(str(a) for a in articles)
            if len(articles) == 1:
                line += f", Điều {arts_str}"
            else:
                line += f", các Điều {arts_str}"

        lines.append(f"• {line}")

    return "\n\n".join(lines)

# ========================================
# TIỆN ÍCH 3: PHÁT HIỆN NGÔN NGỮ
# ========================================
def detect_language(text: str) -> str:
    if not text:
        return "vi"
    if re.search(r'[ăâđêôơưàáảãạầấẩẫậằắẳẵặềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]', text, re.IGNORECASE):
        return "vi"
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
        return "ja"
    return "vi"

_LANG_INSTRUCTION = {
    "en": "Please answer in English.",
    "zh": "请用中文回答。",
    "ko": "한국어로 답변해주세요.",
    "ja": "日本語で答えてください。",
    "vi": "Hãy trả lời bằng tiếng Việt.",
}

_LANG_LABEL = {
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "中文",
    "ko": "한국어",
    "ja": "日本語",
}

# ========================================
# TIỆN ÍCH 4: LƯU LỊCH SỬ
# ========================================
def save_to_history(query: str, answer_preview: str):
    if "history" not in st.session_state:
        st.session_state.history = []

    st.session_state.history.insert(0, {
        "query": query[:150],
        "answer_preview": answer_preview[:200],
        "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
        "timestamp": datetime.now().timestamp()
    })

    if len(st.session_state.history) > 30:
        st.session_state.history = st.session_state.history[:30]

    os.makedirs("data/state", exist_ok=True)
    try:
        with open("data/state/history.json", "w", encoding="utf-8") as f:
            json.dump(st.session_state.history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_history_from_file():
    history_file = "data/state/history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                st.session_state.history = json.load(f)
            return
        except Exception:
            pass
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
            except Exception:
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
        except Exception:
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
# CSS (đã sửa lỗi selector)
# ========================================
st.markdown("""
<style>
[data-testid="stSidebar"] {
    min-width: 320px;
    max-width: 380px;
}

.time-info { font-size: 1rem; line-height: 1.8; margin-bottom: 10px; }
.weather-card {
    background-color: #f0f2f6;
    padding: 10px 5px; border-radius: 10px;
    text-align: center; border: 1px solid #e0e0e0;
}
.weather-temp { font-size: 1.3rem; font-weight: bold; color: #1e1e1e; }
.weather-condition { font-size: 0.8rem; color: #333333; margin-top: 4px; }

/* Thêm padding dưới cùng để chat input không che nội dung */
.block-container {
    padding-bottom: 100px !important;
}
</style>
""", unsafe_allow_html=True)

# ========================================
# KHỞI TẠO SESSION STATE
# ========================================
init_view_counter()
load_history_from_file()

for key, default in [
    ("messages", []),
    ("is_processing", False),
    ("file_content", ""),
    ("pending_file_name", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

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
        <b>🕐 Giờ Hà Nội:</b> <span style="font-size:1.1rem;">{hanoi_time.strftime("%H:%M:%S")}</span><br>
        <b>📆 Dương lịch:</b> <span style="font-size:1rem;">{hanoi_time.strftime("%d/%m/%Y")}</span><br>
        <b>📖 Âm lịch:</b> <span style="font-size:1rem;">{lunar_date}</span>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    # Thời tiết
    st.markdown("### 🌡️ Thời tiết hôm nay")
    cols = st.columns(3)
    for idx, city in enumerate(["Hà Nội", "Nha Trang", "TP. HCM"]):
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
    c1, c2 = st.columns(2)
    c1.metric("👁️ Hôm nay", f"{st.session_state.view_count:,}")
    c2.metric("📊 Tổng", f"{st.session_state.total_views:,}")
    if "history" in st.session_state:
        st.metric("❓ Câu hỏi đã hỏi", len(st.session_state.history))
    st.divider()

    # File uploader
    st.markdown("### 📎 Đính kèm tài liệu")
    uploaded_file = st.file_uploader(
        "Chọn file (PDF, DOCX, TXT)",
        type=["pdf", "docx", "txt"],
        label_visibility="visible",
        key="file_uploader"
    )
    if uploaded_file is not None:
        try:
            from io import BytesIO
            from PyPDF2 import PdfReader
            from docx import Document as DocxDocument

            if uploaded_file.name.endswith('.txt'):
                file_content = uploaded_file.read().decode("utf-8")
            elif uploaded_file.name.endswith('.pdf'):
                reader = PdfReader(BytesIO(uploaded_file.read()))
                file_content = "".join(p.extract_text() or "" for p in reader.pages)
            else:
                doc = DocxDocument(BytesIO(uploaded_file.read()))
                file_content = "\n".join(p.text for p in doc.paragraphs)

            st.session_state.file_content = file_content[:5000]
            st.session_state.pending_file_name = uploaded_file.name
            st.success(f"✅ {uploaded_file.name} ({len(file_content):,} ký tự)")
        except Exception as e:
            st.error(f"Lỗi đọc file: {e}")

    if st.session_state.file_content and st.button("🗑️ Xóa file", use_container_width=True):
        st.session_state.file_content = ""
        st.session_state.pending_file_name = ""
        st.rerun()

    st.divider()

    # Lịch sử
    st.markdown("### 📜 Lịch sử câu hỏi")
    if st.session_state.get("history"):
        if st.button("🗑️ Xóa lịch sử", key="clear_history", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        for item in st.session_state.history[:10]:
            with st.expander(f"📌 {item['time'][:10]}..."):
                st.caption(f"**Câu hỏi:** {item['query']}")
                st.caption(f"**Trả lời:** {item['answer_preview']}...")
    else:
        st.info("💬 Chưa có câu hỏi nào")
    st.divider()

    if st.button("🔑 Kiểm tra API Key", use_container_width=True):
        if GEMINI_API_KEY:
            st.success("✅ API Key đã cấu hình")
        else:
            st.error("❌ Chưa có API Key")

    st.caption("⚖️ Legal AI VN v1.1")

# ========================================
# MAIN CONTENT
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh dựa trên văn bản gốc")

if not PIPELINE_OK:
    st.error(f"❌ Lỗi khởi tạo pipeline: {PIPELINE_ERROR}")
    st.stop()

if not GEMINI_API_KEY:
    st.error("❌ Chưa thiết lập GEMINI_API_KEY.")
    st.stop()

# Hiển thị file đính kèm hiện tại
if st.session_state.file_content:
    st.info(f"📎 Đã đính kèm: **{st.session_state.pending_file_name}** ({len(st.session_state.file_content):,} ký tự)")

# Lịch sử chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.markdown(msg["content"])

# ========================================
# CHAT INPUT
# ========================================
query = st.chat_input(
    "Nhập câu hỏi pháp luật...",
    disabled=st.session_state.is_processing
)

# ========================================
# XỬ LÝ CÂU HỎI
# ========================================
if query and not st.session_state.is_processing:
    st.session_state.is_processing = True

    # Hiển thị câu hỏi
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").write(query)

    # Kết hợp file content
    full_query = query
    if st.session_state.file_content:
        full_query = query + f"\n\n[Nội dung file đính kèm]:\n{st.session_state.file_content}\n"

    # Phát hiện ngôn ngữ
    detected_lang = detect_language(query)
    lang_name = _LANG_LABEL.get(detected_lang, "Tiếng Việt")
    lang_instruction = _LANG_INSTRUCTION.get(detected_lang, _LANG_INSTRUCTION["vi"])
    full_query = full_query.strip() + f"\n\n{lang_instruction}"

    # Gọi pipeline
    with st.spinner(f"⚖️ Đang tra cứu... ({lang_name})"):
        start_time = time.time()
        try:
            result = ask_legal_ai(query=full_query, top_k=8, threshold=0.45)
            latency = round(time.time() - start_time, 2)

            if result.get("status") == "ok":
                retrieved_chunks = result.get("retrieved_chunks", [])
                
                # Xử lý căn cứ pháp lý
                doc_articles = extract_articles_from_chunks(retrieved_chunks)
                legal_basis = format_legal_basis(doc_articles)

                # Lấy phần trả lời chính
                answer_text = result.get("answer", "")
                if "CĂN CỨ PHÁP LÝ" in answer_text:
                    main_answer = answer_text.split("CĂN CỨ PHÁP LÝ")[0].strip()
                else:
                    main_answer = answer_text
                
                if not main_answer:
                    main_answer = answer_text

                final_response = (
                    f"**Trả lời:**\n\n{main_answer}\n\n"
                    f"---\n**📚 Căn cứ pháp lý:**\n\n{legal_basis}\n\n"
                    f"---\n⏱️ {latency}s | 🌐 {lang_name}"
                )
                save_to_history(query, final_response[:200])

            elif result.get("status") in ("out_of_scope", "no_result"):
                final_response = f"⚠️ {result.get('message', 'Không tìm thấy thông tin phù hợp.')}"
            else:
                final_response = f"❌ {result.get('message', 'Có lỗi xảy ra')}"

        except Exception as e:
            final_response = f"❌ Lỗi: {str(e)}"
            print(f"Error: {e}")

    # Hiển thị response
    st.session_state.messages.append({"role": "assistant", "content": final_response})
    with st.chat_message("assistant"):
        st.markdown(final_response)

    # Reset file
    st.session_state.file_content = ""
    st.session_state.pending_file_name = ""
    st.session_state.is_processing = False
    st.rerun()

# Nút dừng (chỉ hiển thị khi đang xử lý)
if st.session_state.is_processing:
    if st.button("⏹️ Dừng tạo câu trả lời", use_container_width=True):
        st.session_state.is_processing = False
        st.rerun()

# Footer
st.divider()
st.caption("⚠️ Thông tin mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
