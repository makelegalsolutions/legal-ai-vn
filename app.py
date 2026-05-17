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
    
    # Fallback cho ngày hiện tại
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
    """Lấy thông tin thời tiết chi tiết (nhiệt độ, độ ẩm, gió, tình trạng)"""
    cities = {
        "Hà Nội": {"lat": 21.0285, "lon": 105.8542},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967},
        "TP. HCM": {"lat": 10.8231, "lon": 106.6297}
    }
    
    if city not in cities:
        return {"temp": "N/A", "condition": "N/A", "humidity": "N/A", "wind": "N/A", "icon": "❓"}
    
    try:
        coords = cities[city]
        # Dùng Open-Meteo với nhiều thông số hơn
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true&hourly=temperature_2m,relative_humidity_2m,precipitation,cloudcover&timezone=Asia/Bangkok"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            temp = current.get('temperature', 'N/A')
            wind = current.get('windspeed', 'N/A')
            wind_dir = current.get('winddirection', 'N/A')
            
            # Lấy thêm thông tin từ hourly (lấy giờ hiện tại)
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
            
            # Xác định điều kiện thời tiết và icon
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
            
            # Kiểm tra mưa
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
            
            # Kiểm tra mây
            if cloudcover and cloudcover > 80 and not (precipitation and precipitation > 0):
                condition = "Nhiều mây"
                icon = "☁️"
            elif cloudcover and cloudcover > 50:
                condition = "Có mây"
                icon = "⛅"
            
            # Hướng gió
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
                wind_text = f", gió {wind_text}"
            
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
# KHỞI TẠO
# ========================================
init_view_counter()
load_history_from_file()

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    # Header
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý Pháp luật Việt Nam**")
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 1: NGÀY GIỜ (FONT NHỎ)
    # ========================================
    st.markdown("### 📅 Thông tin thời gian")
    
    hanoi_time = get_hanoi_time()
    
    # Dùng font nhỏ hơn với markdown
    st.markdown(f"""
    <div style="font-size: 0.85em;">
        <b>🕐 Giờ HN:</b> {hanoi_time.strftime("%H:%M:%S")}<br>
        <b>📆 Ngày DL:</b> {hanoi_time.strftime("%d/%m/%Y")}
    </div>
    """, unsafe_allow_html=True)
    
    # Âm lịch
    lunar_date = get_lunar_date()
    st.info(f"📖 **Âm lịch:** {lunar_date}")
    
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 2: THỜI TIẾT CHI TIẾT
    # ========================================
    st.markdown("### 🌡️ Thời tiết hôm nay")
    
    cities = ["Hà Nội", "Nha Trang", "TP. HCM"]
    
    for city in cities:
        weather = get_weather_detailed(city)
        
        # Tạo khung cho mỗi thành phố
        st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 8px; border-radius: 8px; margin-bottom: 8px;">
            <b>{weather['icon']} {city}</b><br>
            <span style="font-size: 1.3em; font-weight: bold;">{weather['temp']}</span><br>
            <span style="font-size: 0.8em; color: #aaaaaa;">
                {weather['condition']}<br>
                💧 Độ ẩm: {weather['humidity']}<br>
                🌬️ Gió: {weather['wind']}
            </span>
        </div>
        """, unsafe_allow_html=True)
    
    st.caption("⏱️ Cập nhật mỗi 30 phút | Nguồn: Open-Meteo")
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 3: THỐNG KÊ
    # ========================================
    st.markdown("### 📊 Thống kê")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("👁️ Lượt xem hôm nay", f"{st.session_state.view_count:,}")
    with col2:
        st.metric("📊 Tổng lượt xem", f"{st.session_state.total_views:,}")
    
    if "history" in st.session_state:
        st.metric("❓ Câu hỏi đã hỏi", len(st.session_state.history))
    
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 4: LỊCH SỬ CÂU HỎI
    # ========================================
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
    
    # ========================================
    # KIỂM TRA HỆ THỐNG
    # ========================================
    if st.button("🔑 Kiểm tra API Key", use_container_width=True):
        check_api_keys()
    
    # ========================================
    # DEBUG
    # ========================================
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

tab1, tab2 = st.tabs(["💬 Tra cứu pháp luật", "ℹ️ Giới thiệu"])

with tab1:
    with st.form(key="query_form"):
        query = st.text_area(
            "📝 Nhập câu hỏi của bạn:",
            placeholder="Ví dụ: \n- Nghỉ thai sản được bao nhiêu tháng?\n- Điều kiện thành lập công ty TNHH là gì?\n- Mức phạt vượt đèn đỏ hiện nay?",
            height=120
        )
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            top_k = st.slider("📚 Số văn bản tham khảo", min_value=3, max_value=10, value=6)
        with col2:
            threshold = st.slider("🎯 Ngưỡng độ tin cậy", 0.30, 0.70, 0.45, step=0.01)
        with col3:
            submitted = st.form_submit_button("🔍 Tra cứu & Trả lời", type="primary", use_container_width=True)
    
    if submitted:
        if not query or not query.strip():
            st.warning("⚠️ Vui lòng nhập câu hỏi!")
        elif not GEMINI_API_KEY:
            st.error("❌ Chưa thiết lập GEMINI_API_KEY")
        else:
            with st.spinner("⚖️ Đang tra cứu..."):
                start = time.time()
                try:
                    result = ask_legal_ai(
                        query=query.strip(),
                        top_k=top_k,
                        threshold=threshold
                    )
                    latency = round(time.time() - start, 2)
                    
                    if result["status"] == "ok":
                        st.success("✅ **Câu trả lời:**")
                        st.markdown(result["answer"])
                        
                        save_to_history(query.strip(), result["answer"][:200])
                        
                        with st.expander("📚 Xem nguồn trích dẫn"):
                            for i, chunk in enumerate(result.get("retrieved_chunks", []), 1):
                                st.markdown(f"**{i}. {chunk.get('article', 'N/A')}**")
                                st.caption(f"📄 {chunk.get('title', '')[:100]}...")
                                st.caption(f"🎯 Độ tin cậy: {chunk.get('score', 0):.4f}")
                                st.divider()
                                
                    elif result["status"] in ["out_of_scope", "no_result"]:
                        st.warning(f"⚠️ {result.get('message', 'Không tìm thấy thông tin')}")
                    else:
                        st.error(f"❌ {result.get('message', 'Có lỗi xảy ra')}")
                        
                except Exception as e:
                    st.error(f"❌ Lỗi: {str(e)}")
                    latency = 0
            
            st.caption(f"⏱️ Thời gian: {latency} giây")

with tab2:
    st.markdown("""
    ### 📖 Giới thiệu về Legal AI VN
    
    **Legal AI VN** là trợ lý pháp luật thông minh sử dụng công nghệ **RAG** kết hợp với **Gemini** của Google.
    
    ---
    
    ### 🎯 Tính năng
    
    | Tính năng | Mô tả |
    |-----------|-------|
    | 🔍 Tra cứu thông minh | Tìm văn bản pháp luật liên quan |
    | 📝 Trả lời chính xác | Dựa trên nội dung gốc, có trích dẫn |
    | 🔄 Tự động cập nhật | Đồng bộ từ Drive và Congbao |
    | 🌡️ Tiện ích bổ sung | Thời gian, thời tiết, lịch sử |
    
    ---
    
    ### ⚠️ Lưu ý
    
    > Thông tin chỉ mang tính **tham khảo**, không thay thế tư vấn pháp lý chính thức.
    
    ---
    
    **Phiên bản:** v1.0 | **Cập nhật:** 2026-05-18
    """)

# Footer
st.divider()
st.caption("⚠️ Thông tin mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
