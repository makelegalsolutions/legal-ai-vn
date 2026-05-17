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
@st.cache_data(ttl=3600)  # Cache 1 giờ
def get_lunar_date():
    """Lấy ngày âm lịch từ API (dùng free API)"""
    try:
        today = datetime.now()
        # Dùng API âm lịch miễn phí
        url = f"https://v2.baolau.com/lunar?day={today.day}&month={today.month}&year={today.year}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            lunar_day = data.get('lunarDay', '')
            lunar_month = data.get('lunarMonth', '')
            lunar_year = data.get('lunarYear', '')
            if lunar_day and lunar_month and lunar_year:
                return f"Ngày {lunar_day} tháng {lunar_month} năm {lunar_year}"
    except:
        pass
    
    # Fallback: tính đơn giản (không chính xác 100%, nhưng tạm dùng)
    try:
        from datetime import date
        # Ngày âm lịch mẫu cho ngày 17/05/2026 (cập nhật thủ công nếu cần)
        # Bạn có thể thay bằng API khác hoặc bỏ qua
        return "Đang cập nhật"
    except:
        return "Đang cập nhật"

# ========================================
# TIỆN ÍCH 1C: LẤY NHIỆT ĐỘ CÁC THÀNH PHỐ
# ========================================
@st.cache_data(ttl=1800)  # Cache 30 phút
def get_weather(city: str) -> dict:
    """Lấy nhiệt độ từ Open-Meteo API (miễn phí, không cần key)"""
    cities = {
        "Hà Nội": {"lat": 21.0285, "lon": 105.8542, "name": "Hà Nội"},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967, "name": "Nha Trang"},
        "TP. Hồ Chí Minh": {"lat": 10.8231, "lon": 106.6297, "name": "TP. HCM"}
    }
    
    if city not in cities:
        return {"temp": "N/A", "condition": "N/A"}
    
    try:
        coords = cities[city]
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true&timezone=Asia/Bangkok"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            temp = current.get('temperature', 'N/A')
            wind = current.get('windspeed', 'N/A')
            
            # Xác định điều kiện thời tiết đơn giản
            condition = "☀️ Nắng" if temp > 28 else "🌤️ Mát" if temp > 22 else "🌥️ Se lạnh"
            if wind > 20:
                condition = "💨 Gió mạnh"
            
            return {"temp": f"{temp}°C", "condition": condition}
    except:
        pass
    
    return {"temp": "N/A", "condition": "N/A"}

# ========================================
# TIỆN ÍCH 2A: LƯU LỊCH SỬ CÂU HỎI
# ========================================
def save_to_history(query: str, answer_preview: str):
    """Lưu câu hỏi vào lịch sử (session state và file)"""
    # Khởi tạo session state
    if "history" not in st.session_state:
        st.session_state.history = []
    
    # Thêm câu hỏi mới
    new_item = {
        "query": query[:150],
        "answer_preview": answer_preview[:200],
        "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
        "timestamp": datetime.now().timestamp()
    }
    st.session_state.history.insert(0, new_item)
    
    # Chỉ giữ 30 câu hỏi gần nhất
    if len(st.session_state.history) > 30:
        st.session_state.history = st.session_state.history[:30]
    
    # Lưu vào file để persistent
    os.makedirs("data/state", exist_ok=True)
    history_file = "data/state/history.json"
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(st.session_state.history, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_history_from_file():
    """Tải lịch sử từ file khi khởi động"""
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
    """Khởi tạo view counter trong session state và file"""
    counter_file = "data/state/view_count.json"
    
    # Khởi tạo session state
    if "view_count" not in st.session_state:
        # Đọc từ file nếu có
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
        
        # Tăng lượt view cho session mới
        st.session_state.view_count += 1
        st.session_state.total_views += 1
        
        # Lưu lại file
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
    from pipeline.search_pipeline import legal_search
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
# KHỞI TẠO VIEW COUNTER & HISTORY
# ========================================
init_view_counter()
load_history_from_file()

# ========================================
# SIDEBAR - TIỆN ÍCH 1: THỜI TIẾT & THỜI GIAN
# ========================================
with st.sidebar:
    # Header
    st.title("⚖️ Legal AI VN")
    st.markdown("**Trợ lý Pháp luật Việt Nam**")
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 1: NGÀY GIỜ HÀ NỘI (Dương lịch + Âm lịch)
    # ========================================
    st.markdown("### 📅 Thông tin thời gian")
    
    hanoi_time = get_hanoi_time()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("🕐 Giờ HN", hanoi_time.strftime("%H:%M:%S"))
    with col2:
        st.metric("📆 Ngày DL", hanoi_time.strftime("%d/%m/%Y"))
    
    # Âm lịch
    lunar_date = get_lunar_date()
    st.caption(f"📖 {lunar_date}")
    
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 1C: NHIỆT ĐỘ CÁC THÀNH PHỐ
    # ========================================
    st.markdown("### 🌡️ Nhiệt độ hôm nay")
    
    cities = ["Hà Nội", "Nha Trang", "TP. Hồ Chí Minh"]
    
    for city in cities:
        weather = get_weather(city)
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            st.write(f"**{city}**")
        with col2:
            st.write(weather["temp"])
        with col3:
            st.caption(weather["condition"])
    
    st.caption("⏱️ Cập nhật mỗi 30 phút | ☁️ Nguồn: Open-Meteo")
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 2A + 2B: THỐNG KÊ & LƯỢT VIEW
    # ========================================
    st.markdown("### 📊 Thống kê")
    
    # Số lượt view
    col1, col2 = st.columns(2)
    with col1:
        st.metric("👁️ Lượt xem hôm nay", f"{st.session_state.view_count:,}")
    with col2:
        st.metric("📊 Tổng lượt xem", f"{st.session_state.total_views:,}")
    
    # Số câu hỏi đã hỏi
    if "history" in st.session_state:
        st.metric("❓ Câu hỏi đã hỏi", len(st.session_state.history))
    
    st.divider()
    
    # ========================================
    # TIỆN ÍCH 2C: LỊCH SỬ CÂU HỎI
    # ========================================
    st.markdown("### 📜 Lịch sử câu hỏi")
    
    if "history" in st.session_state and st.session_state.history:
        # Nút xóa lịch sử
        if st.button("🗑️ Xóa lịch sử", key="clear_history"):
            st.session_state.history = []
            history_file = "data/state/history.json"
            if os.path.exists(history_file):
                os.remove(history_file)
            st.rerun()
        
        # Hiển thị lịch sử
        for i, item in enumerate(st.session_state.history[:15]):
            with st.expander(f"📌 {item['time'][:10]}..."):
                st.caption(f"**Câu hỏi:** {item['query']}")
                st.caption(f"**Trả lời:** {item['answer_preview']}...")
    else:
        st.info("💬 Chưa có câu hỏi nào")
        st.caption("Hãy đặt câu hỏi pháp luật ở phần chính")
    
    st.divider()
    
    # ========================================
    # KIỂM TRA HỆ THỐNG
    # ========================================
    if st.button("🔑 Kiểm tra API Key"):
        check_api_keys()
    
    # ========================================
    # DEBUG: KIỂM TRA DỮ LIỆU
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
        
        # Version
        version_file = "data/vectorstore/latest_version.txt"
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                version = f.read().strip()
            st.info(f"📌 Version: {version[:20]}..." if len(version) > 20 else f"📌 Version: {version}")
    
    # Footer
    st.divider()
    st.caption("⚖️ Legal AI VN v1.0")

# ========================================
# MAIN INTERFACE
# ========================================
st.title("⚖️ Legal AI Việt Nam")
st.markdown("Hỏi đáp pháp luật thông minh dựa trên văn bản gốc")

# Tabs cho các chức năng
tab1, tab2 = st.tabs(["💬 Tra cứu pháp luật", "ℹ️ Giới thiệu & Hướng dẫn"])

with tab1:
    # Form nhập câu hỏi
    with st.form(key="query_form"):
        query = st.text_area(
            "📝 Nhập câu hỏi của bạn:",
            placeholder="Ví dụ: \n- Nghỉ thai sản được bao nhiêu tháng?\n- Điều kiện thành lập công ty TNHH là gì?\n- Mức phạt vượt đèn đỏ hiện nay?",
            height=120
        )
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            top_k = st.slider("📚 Số văn bản tham khảo", min_value=3, max_value=10, value=6, help="Càng nhiều càng chính xác nhưng chậm hơn")
        with col2:
            threshold = st.slider("🎯 Ngưỡng độ tin cậy", 0.30, 0.70, 0.45, step=0.01, help="Cao hơn = chính xác hơn nhưng có thể bỏ lỡ thông tin")
        with col3:
            submitted = st.form_submit_button("🔍 Tra cứu & Trả lời", type="primary", use_container_width=True)
    
    if submitted:
        if not query or not query.strip():
            st.warning("⚠️ Vui lòng nhập câu hỏi!")
        elif not GEMINI_API_KEY:
            st.error("❌ Chưa thiết lập GEMINI_API_KEY. Vui lòng kiểm tra Settings → Secrets trên Streamlit Cloud.")
        else:
            with st.spinner("⚖️ Đang tra cứu văn bản pháp luật và phân tích..."):
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
                        
                        # Lưu vào lịch sử
                        save_to_history(query.strip(), result["answer"][:200])
                        
                        with st.expander("📚 Xem nguồn trích dẫn pháp lý"):
                            for i, chunk in enumerate(result.get("retrieved_chunks", []), 1):
                                st.markdown(f"**{i}. {chunk.get('article', 'N/A')}**")
                                st.caption(f"📄 Văn bản: {chunk.get('title', '')[:100]}...")
                                st.caption(f"🎯 Độ tin cậy: {chunk.get('score', 0):.4f}")
                                st.divider()
                                
                    elif result["status"] in ["out_of_scope", "no_result"]:
                        st.warning(f"⚠️ {result.get('message', 'Không tìm thấy thông tin phù hợp.')}")
                        st.info("💡 Gợi ý: Hãy thử hỏi về các lĩnh vực như doanh nghiệp, lao động, hành chính...")
                    else:
                        st.error(f"❌ {result.get('message', 'Có lỗi xảy ra khi xử lý.')}")
                        
                except Exception as e:
                    st.error(f"❌ Lỗi xử lý: {str(e)}")
                    latency = 0
            
            st.caption(f"⏱️ Thời gian xử lý: {latency} giây")

with tab2:
    st.markdown("""
    ### 📖 Giới thiệu về Legal AI VN
    
    **Legal AI VN** là trợ lý pháp luật thông minh sử dụng công nghệ **RAG (Retrieval-Augmented Generation)** kết hợp với mô hình ngôn ngữ lớn **Gemini** của Google.
    
    ---
    
    ### 🎯 Tính năng chính
    
    | Tính năng | Mô tả |
    |-----------|-------|
    | 🔍 Tra cứu thông minh | Tìm kiếm văn bản pháp luật liên quan đến câu hỏi |
    | 📝 Trả lời chính xác | Dựa trên nội dung văn bản gốc, có trích dẫn cụ thể |
    | 📚 Nguồn trích dẫn | Hiển thị Điều, Khoản, văn bản nguồn |
    | 🔄 Tự động cập nhật | Đồng bộ dữ liệu từ Google Drive và Congbao mỗi 6 giờ |
    | 🌡️ Tiện ích bổ sung | Thời gian, thời tiết, lịch sử câu hỏi |
    
    ---
    
    ### 📚 Nguồn dữ liệu
    
    - **Google Drive**: Văn bản pháp luật đã được tải lên
    - **Congbao.chinhphu.vn**: Crawler tự động lấy văn bản mới
    - **Định dạng**: PDF, DOCX
    
    ---
    
    ### 💡 Cách sử dụng hiệu quả
    
    1. **Đặt câu hỏi cụ thể**, rõ ràng
    2. **Tham khảo ngưỡng tin cậy** (cao hơn = chính xác hơn)
    3. **Xem nguồn trích dẫn** để kiểm tra thông tin gốc
    4. **Sử dụng lịch sử** để xem lại câu hỏi đã hỏi
    
    ---
    
    ### ⚠️ Lưu ý quan trọng
    
    > Thông tin do AI tạo ra chỉ mang tính **tham khảo**, không thay thế tư vấn pháp lý chính thức từ luật sư hoặc cơ quan nhà nước có thẩm quyền.
    
    ---
    
    ### 📞 Liên hệ & Đóng góp
    
    - **GitHub**: [makelegalsolutions/legal-ai-vn](https://github.com/makelegalsolutions/legal-ai-vn)
    - **Báo lỗi**: Tạo issue trên GitHub
    - **Đóng góp dữ liệu**: Gửi văn bản pháp luật qua Google Drive
    
    ---
    
    ### 📊 Phiên bản
    
    | Thông tin | Chi tiết |
    |-----------|----------|
    | Phiên bản | v1.0 |
    | Cập nhật cuối | 2026-05-17 |
    | Engine AI | Gemini 2.5 Flash |
    | Embedding | multilingual-e5-base |
    """)

# Footer
st.divider()
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.caption("⚠️ Thông tin mang tính tham khảo. Không thay thế tư vấn pháp lý chính thức.")
    st.caption("⚖️ Legal AI VN - Trợ lý Pháp luật Việt Nam")
