import sys
from pathlib import Path
import os
import json
from datetime import datetime
import requests

# ==================== FIX IMPORT CHO STREAMLIT CLOUD ====================
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))
# =====================================================================

import streamlit as st
import time

# ========================================
# TIỆN ÍCH 1A: LẤY NGÀY GIỜ HÀ NỘI
# ========================================
def get_hanoi_time():
    """Lấy thời gian hiện tại theo múi giờ Hà Nội (UTC+7)"""
    from datetime import timezone, timedelta
    tz_hanoi = timezone(timedelta(hours=7))
    return datetime.now(tz_hanoi)

# ========================================
# TIỆN ÍCH 1B: LẤY NGÀY ÂM LỊCH
# ========================================
@st.cache_data(ttl=3600)
def get_lunar_date():
    """Lấy ngày âm lịch từ API"""
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
    
    try:
        today = datetime.now()
        url = f"https://api.vietlunar.com/v1/calendar?day={today.day}&month={today.month}&year={today.year}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            lunar_day = data.get('lunarDay', '')
            lunar_month = data.get('lunarMonth', '')
            lunar_year = data.get('lunarYear', '')
            if lunar_day and lunar_month and lunar_year:
                return f"Ngày {lunar_day} tháng {lunar_month} năm {lunar_year}"
    except:
        pass
    
    today = datetime.now()
    if today.year == 2026 and today.month == 5 and today.day == 18:
        return "Ngày 22 tháng 3 năm Ất Tỵ"
    elif today.year == 2026 and today.month == 5 and today.day == 17:
        return "Ngày 21 tháng 3 năm Ất Tỵ"
    else:
        return f"Đang cập nhật"

# ========================================
# TIỆN ÍCH 1C: LẤY THÔNG TIN THỜI TIẾT CHI TIẾT
# ========================================
@st.cache_data(ttl=1800)
def get_weather_detailed(city: str) -> dict:
    """Lấy thông tin thời tiết chi tiết"""
    cities = {
        "Hà Nội": {"lat": 21.0285, "lon": 105.8542},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967},
        "TP. HCM": {"lat": 10.8231, "lon": 106.6297}
    }
    
    if city not in cities:
        return {"temp": "N/A", "condition": "N/A", "humidity": "N/A", "wind": "N/A", "icon": "❓"}
    
    try:
        coords = cities[city]
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true&hourly=temperature_2m,relative_humidity_2m,precipitation,cloudcover&timezone=Asia/Bangkok"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            temp = current.get('temperature', 'N/A')
            wind = current.get('windspeed', 'N/A')
            wind_dir = current.get('winddirection', 'N/A')
            
            hourly = data.get('hourly', {})
            current_hour = datetime.now().hour
            humidity = "N/A"
            precipitation = "N/A"
            cloudcover = "N/A"
            
            if hourly:
                times = hourly.get('time', [])
                for i, t in enumerate(times):
                    if t and current_hour in [int(t.split('T')[1].split(':')[0]) if 'T' in t else -1]:
                        if i < len(hourly.get('relative_humidity_2m', [])):
                            humidity = hourly['relative_humidity_2m'][i]
                        if i < len(hourly.get('precipitation', [])):
                            precipitation = hourly['precipitation'][i]
                        if i < len(hourly.get('cloudcover', [])):
                            cloudcover = hourly['cloudcover'][i]
                        break
            
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
            
            if precipitation and precipitation > 0:
                if precipitation < 2:
                    condition = "Mưa nhỏ"
                    icon = "🌦️"
                elif precipitation < 10:
                    condition = "Mưa vừa"
                    icon = "🌧️"
                else:
                    condition = "Mưa lớn"
                    icon = "⛈️"
            
            if cloudcover and cloudcover > 80 and not (precipitation and precipitation > 0):
                condition = "Nhiều mây"
                icon = "☁️"
            elif cloudcover and cloudcover > 50:
                condition = "Có mây"
                icon = "⛅"
            
            wind_text = ""
            if wind_dir != 'N/A':
                if 0 <= wind_dir < 22.5 or 337.5 <= wind_dir <= 360:
                    wind_text = "Bắc"
                elif 22.5 <= wind_dir < 67.5:
                    wind_text = "Đông Bắc"
                elif 67.5 <= wind_dir < 112.5:
                    wind_text = "Đông"
                elif 112.5 <= wind_dir < 157.5:
                    wind_text = "Đông Nam"
                elif 157.5 <= wind_dir < 202.5:
                    wind_text = "Nam"
                elif 202.5 <= wind_dir < 247.5:
                    wind_text = "Tây Nam"
                elif 247.5 <= wind_dir < 292.5:
                    wind_text = "Tây"
                elif 292.5 <= wind_dir < 337.5:
                    wind_text = "Tây Bắc"
                wind_text = f", {wind_text}"
            
            return {
                "temp": f"{temp}°C" if temp != 'N/A' else "N/A",
                "condition": condition,
                "icon": icon,
                "humidity": f"{humidity}%" if humidity != 'N/A' else "N/A",
                "wind": f"{wind} km/h{wind_text}" if wind != 'N/A' else "N/A",
                "precipitation": f"{precipitation} mm" if precipitation != 'N/A' else "N/A"
            }
    except Exception as e:
        print(f"Weather error for {city}: {e}")
    
    return {"temp": "N/A", "condition": "N/A", "icon": "❓", "humidity": "N/A", "wind": "N/A", "precipitation": "N/A"}

# ========================================
# TIỆN ÍCH 2A: LƯU LỊCH SỬ CÂU HỎI
# ========================================
def save_to_history(query: str, answer_preview: str):
    """Lưu câu hỏi vào lịch sử"""
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
    """Tải lịch sử từ file"""
    history_file = "data/state/history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                st.session_state.history = json.load(f)
        except:
            st.session_state.history = []
    else:
        st.session_state.history = []

# ========================================
# TIỆN ÍCH 2B: ĐẾM LƯỢT VIEW
# ========================================
def init_view_counter():
    """Khởi tạo view counter"""
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
# TIỆN ÍCH 3: XỬ LÝ FILE ĐÍNH KÈM
# ========================================
def read_uploaded_file(uploaded_file):
    """Đọc nội dung file đính kèm (PDF, DOCX, TXT)"""
    if uploaded_file is None:
        return ""
    
    try:
        file_type = uploaded_file.type
        file_name = uploaded_file.name
        
        if file_type == "text/plain" or file_name.endswith('.txt'):
            return uploaded_file.read().decode("utf-8")
        
        elif file_type == "application/pdf" or file_name.endswith('.pdf'):
            from PyPDF2 import PdfReader
            import io
            pdf_bytes = io.BytesIO(uploaded_file.read())
            reader = PdfReader(pdf_bytes)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text[:5000]  # Giới hạn 5000 ký tự
        
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or file_name.endswith('.docx'):
            from docx import Document
            import io
            docx_bytes = io.BytesIO(uploaded_file.read())
            doc = Document(docx_bytes)
            text = "\n".join([p.text for p in doc.paragraphs])
            return text[:5000]
        
        else:
            return f"⚠️ Không hỗ trợ định dạng file: {file_type}"
    
    except Exception as e:
        return f"❌ Lỗi đọc file: {str(e)}"

def format_legal_citations(chunks):
    """Định dạng căn cứ pháp lý từ các chunks trả về"""
    citations = []
    seen = set()
    
    for chunk in chunks:
        # Tạo key duy nhất để tránh trùng lặp
        key = f"{chunk.get('doc_id', '')}_{chunk.get('article', '')}"
        if key in seen:
            continue
        seen.add(key)
        
        doc_id = chunk.get('doc_id', 'Không rõ')
        article = chunk.get('article', 'Không rõ')
        title = chunk.get('title', '')
        text = chunk.get('text', '')[:300]  # Trích yếu 300 ký tự
        
        citations.append(f"""**{doc_id}**\n- Điều: {article}\n- Trích yếu: {text}...\n""")
    
    return citations

# ========================================
# IMPORT PIPELINE
# ========================================
from pipeline.config import check_api_keys, GEMINI_API_KEY

try:
    from pipeline.llm_pipeline import ask_legal_ai
except Exception as e:
    st.error(f"Lỗi khởi tạo pipeline: {str(e)}")
    st.stop()

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
# CSS TÙY CHỈNH
# ========================================
st.markdown("""
<style>
    /* Tăng độ rộng sidebar */
    [data-testid="stSidebar"] {
        min-width: 320px;
        max-width: 380px;
    }
    
    /* Style cho thời gian */
    .time-info {
        font-size: 1rem;
        line-height: 1.8;
        margin-bottom: 10px;
    }
    
    /* Style cho thời tiết */
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
    .weather-detail {
        font-size: 0.7rem;
        color: #555555;
        margin-top: 6px;
        line-height: 1.4;
    }
    .weather-city {
        font-weight: bold;
        font-size: 0.9rem;
        color: #1e1e1e;
    }
    
    /* Style cho chat input */
    .stTextArea textarea {
        font-size: 1rem;
    }
    
    /* Style cho câu trả lời */
    .answer-box {
        background-color: #f0f7ff;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #0066cc;
        margin-bottom: 20px;
    }
    
    /* Style cho căn cứ pháp lý */
    .legal-basis {
        background-color: #f5f5f5;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin-top: 15px;
    }
    .legal-item {
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)

# ========================================
# KHỞI TẠO
# ========================================
init_view_counter()
load_history_from_file()

# Khởi tạo session state cho chat
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_query" not in st.session_state:
    st.session_state.current_query = ""

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý Pháp luật Việt Nam**")
    st.divider()
    
    # TIỆN ÍCH 1: NGÀY GIỜ
    st.markdown("### 📅 Thông tin thời gian")
    hanoi_time = get_hanoi_time()
    
    st.markdown(f"""
    <div class="time-info">
        <b>🕐 Giờ Hà Nội:</b> <span style="font-size: 1.1rem;">{hanoi_time.strftime("%H:%M:%S")}</span><br>
        <b>📆 Dương lịch:</b> <span style="font-size: 1rem;">{hanoi_time.strftime("%d/%m/%Y")}</span><br>
        <b>📖 Âm lịch:</b> <span style="font-size: 1rem;">{get_lunar_date()}</span>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    # TIỆN ÍCH 2: THỜI TIẾT
    st.markdown("### 🌡️ Thời tiết hôm nay")
    cities = ["Hà Nội", "Nha Trang", "TP. HCM"]
    weather_data = {city: get_weather_detailed(city) for city in cities}
    cols = st.columns(3)
    
    for idx, city in enumerate(cities):
        w = weather_data[city]
        with cols[idx]:
            st.markdown(f"""
            <div class="weather-card">
                <div class="weather-city">{w['icon']} {city}</div>
                <div class="weather-temp">{w['temp']}</div>
                <div class="weather-condition">{w['condition']}</div>
                <div class="weather-detail">
                    💧 {w['humidity']}<br>
                    🌬️ {w['wind']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.caption("⏱️ Cập nhật mỗi 30 phút | Nguồn: Open-Meteo")
    st.divider()
    
    # TIỆN ÍCH 3: THỐNG KÊ
    st.markdown("### 📊 Thống kê")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("👁️ Lượt xem hôm nay", f"{st.session_state.view_count:,}")
    with col2:
        st.metric("📊 Tổng lượt xem", f"{st.session_state.total_views:,}")
    
    if "history" in st.session_state:
        st.metric("❓ Câu hỏi đã hỏi", len(st.session_state.history))
    st.divider()
    
    # TIỆN ÍCH 4: LỊCH SỬ
    st.markdown("### 📜 Lịch sử câu hỏi")
    if "history" in st.session_state and st.session_state.history:
        if st.button("🗑️ Xóa lịch sử", key="clear_history", use_container_width=True):
            st.session_state.history = []
            history_file = "data/state/history.json"
            if os.path.exists(history_file):
                os.remove(history_file)
            st.rerun()
        
        for i, item in enumerate(st.session_state.history[:10]):
            with st.expander(f"📌 {item['time'][:10]}..."):
                st.caption(f"**Câu hỏi:** {item['query']}")
                st.caption(f"**Trả lời:** {item['answer_preview']}...")
    else:
        st.info("💬 Chưa có câu hỏi nào")
    st.divider()
    
    # KIỂM TRA HỆ THỐNG
    if st.button("🔑 Kiểm tra API Key", use_container_width=True):
        check_api_keys()
    
    with st.expander("🔧 System Status"):
        data_paths = {
            "Chunks": "data/chunks/legal_chunks_latest.json",
            "FAISS": "data/vectorstore/legal_index.faiss",
            "Version": "data/vectorstore/latest_version.txt",
            "State": "data/state/processed_files.json"
        }
        for name, path in data_paths.items():
            if os.path.exists(path):
                if path.endswith(".json"):
                    try:
                        with open(path, "r") as f:
                            data = json.load(f)
                            size = len(data) if isinstance(data, list) else len(data.keys())
                        st.success(f"✅ {name}: {size}")
                    except:
                        st.success(f"✅ {name}: OK")
                else:
                    size = os.path.getsize(path) / 1024 / 1024
                    st.success(f"✅ {name}: {size:.1f} MB")
            else:
                st.error(f"❌ {name}: NOT FOUND")
        
        version_file = "data/vectorstore/latest_version.txt"
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                version = f.read().strip()
            st.info(f"📌 Version: {version[:20]}..." if len(version) > 20 else f"📌 Version: {version}")
    
    st.divider()
    st.caption("⚖️ Legal AI VN v1.0")

# ========================================
# MAIN INTERFACE
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh dựa trên văn bản gốc")

# ========================================
# CHAT INTERFACE
# ========================================

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.markdown(msg["content"])

# Chat input với enter và mũi tên lên
query = st.chat_input("Nhập câu hỏi pháp luật của bạn...")

# File uploader
uploaded_file = st.file_uploader(
    "📎 Đính kèm file (PDF, DOCX, TXT) - nội dung sẽ được thêm vào câu hỏi",
    type=["pdf", "docx", "txt"],
    help="Tải lên file văn bản để AI phân tích thêm"
)

# Xử lý khi có câu hỏi
if query:
    # Thêm câu hỏi vào lịch sử chat
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").write(query)
    
    # Xử lý file đính kèm
    file_content = ""
    if uploaded_file is not None:
        file_content = read_uploaded_file(uploaded_file)
        if file_content and not file_content.startswith(("⚠️", "❌")):
            file_content = f"\n\n[Nội dung file đính kèm]:\n{file_content}\n"
    
    # Kết hợp câu hỏi với nội dung file
    full_query = query + file_content if file_content else query
    
    # Kiểm tra API key
    if not GEMINI_API_KEY:
        response = "❌ Chưa thiết lập GEMINI_API_KEY. Vui lòng kiểm tra Settings → Secrets trên Streamlit Cloud."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)
        st.rerun()
    
    # Gọi API
    with st.spinner("⚖️ Đang tra cứu văn bản pháp luật và phân tích..."):
        start = time.time()
        try:
            result = ask_legal_ai(
                query=full_query.strip(),
                top_k=6,
                threshold=0.45
            )
            latency = round(time.time() - start, 2)
            
            if result["status"] == "ok":
                answer_text = result["answer"]
                retrieved_chunks = result.get("retrieved_chunks", [])
                
                # Tách phần trả lời và căn cứ pháp lý
                import re
                # Tìm phần "CĂN CỨ PHÁP LÝ" trong câu trả lời gốc
                legal_basis_section = ""
                main_answer = answer_text
                
                if "CĂN CỨ PHÁP LÝ" in answer_text:
                    parts = answer_text.split("CĂN CỨ PHÁP LÝ")
                    main_answer = parts[0].strip()
                    legal_basis_section = "CĂN CỨ PHÁP LÝ" + parts[1] if len(parts) > 1 else ""
                
                # Định dạng lại căn cứ pháp lý từ chunks
                legal_citations = format_legal_citations(retrieved_chunks)
                
                # Xây dựng response
                final_response = f"""**Trả lời:**

{main_answer}

---
**Căn cứ pháp lý:**

"""
                for citation in legal_citations[:5]:  # Tối đa 5 căn cứ
                    final_response += f"\n{citation}\n"
                
                if not legal_citations:
                    final_response += "\n*Không có trích dẫn cụ thể từ văn bản pháp luật.*\n"
                
                final_response += f"\n---\n⏱️ Thời gian xử lý: {latency} giây"
                
                # Lưu vào lịch sử
                save_to_history(query, final_response[:200])
                
            elif result["status"] in ["out_of_scope", "no_result"]:
                final_response = f"⚠️ {result.get('message', 'Không tìm thấy thông tin phù hợp.')}\n\n💡 Gợi ý: Hãy thử hỏi về các lĩnh vực như doanh nghiệp, lao động, hành chính..."
            else:
                final_response = f"❌ {result.get('message', 'Có lỗi xảy ra khi xử lý.')}"
                
        except Exception as e:
            final_response = f"❌ Lỗi: {str(e)}"
            latency = 0
    
    # Hiển thị response
    st.session_state.messages.append({"role": "assistant", "content": final_response})
    with st.chat_message("assistant"):
        st.markdown(final_response)
    
    st.rerun()

# ========================================
# CLEAR CHAT BUTTON
# ========================================
col1, col2, col3 = st.columns([1, 1, 1])
with col2:
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Footer
st.divider()
st.caption("⚠️ Thông tin mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
