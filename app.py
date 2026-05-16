import streamlit as st
import os
import json
import datetime
import numpy as np
import faiss
import requests
from google import genai
from google.genai import types
from sentence_transformers import SentenceTransformer

# ====================================
# 1. CẤU HÌNH TRANG
# ====================================
st.set_page_config(
    page_title="Trợ Lý Pháp Luật AI",
    page_icon="⚖️",
    layout="wide",  # wide để sidebar rộng hơn
    initial_sidebar_state="expanded",
)

# Mở rộng sidebar bằng CSS
st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            min-width: 320px;
            max-width: 360px;
        }
        [data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem;
        }
        /* Căn đều 3 cột thời tiết */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            gap: 0.3rem;
        }
    </style>
""", unsafe_allow_html=True)

TOP_K      = 5
THRESHOLD  = 0.5
MODEL_NAME = "BAAI/bge-m3"

# ====================================
# 2. SIDEBAR
# ====================================
with st.sidebar:

    # ── Thời gian & lịch ────────────────────
    st.subheader("📆 Thời Gian")
    now = datetime.datetime.now()
    st.markdown(f"🕒 **Giờ Hà Nội:** `{now.strftime('%H:%M:%S')}`")
    st.markdown(f"📅 **Dương lịch:** {now.strftime('%d/%m/%Y')}")

    try:
        from lunarcalendar import Converter, Solar
        lunar = Converter.Solar2Lunar(Solar(now.year, now.month, now.day))
        st.markdown(f"🌙 **Âm lịch:** Ngày {lunar.day} tháng {lunar.month} năm {lunar.year}")
    except ImportError:
        pass

    st.markdown("---")

    # ── Thời tiết 3 thành phố ───────────────
    st.subheader("🌤️ Thời Tiết")

    CITIES = {
        "Hà Nội":   {"lat": 21.0285, "lon": 105.8542, "icon": "🏙️"},
        "Nha Trang": {"lat": 12.2388, "lon": 109.1967, "icon": "🌊"},
        "TP.HCM":   {"lat": 10.8231, "lon": 106.6297, "icon": "🏢"},
    }

    WEATHER_CODE = {
        0: "☀️ Quang đãng", 1: "🌤️ Ít mây", 2: "⛅ Nhiều mây", 3: "☁️ Âm u",
        45: "🌫️ Sương mù",  48: "🌫️ Sương giá",
        51: "🌦️ Mưa phùn",  53: "🌦️ Mưa phùn", 55: "🌧️ Mưa phùn dày",
        61: "🌧️ Mưa nhẹ",   63: "🌧️ Mưa vừa",  65: "🌧️ Mưa to",
        80: "🌦️ Mưa rào",   81: "🌧️ Mưa rào",  82: "⛈️ Mưa rào mạnh",
        95: "⛈️ Dông",      96: "⛈️ Dông đá",   99: "⛈️ Dông đá mạnh",
    }

    @st.cache_data(ttl=1800)
    def lay_thoi_tiet(lat: float, lon: float) -> dict:
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weathercode,windspeed_10m"
                f"&timezone=Asia%2FBangkok"
            )
            data = requests.get(url, timeout=5).json()["current"]
            return {
                "nhiet_do": round(data["temperature_2m"]),
                "mo_ta":    WEATHER_CODE.get(data["weathercode"], "–"),
                "gio":      round(data["windspeed_10m"]),
                "ok":       True,
            }
        except Exception:
            return {"ok": False}

    c1, c2, c3 = st.columns(3)
    for col, (city, info) in zip([c1, c2, c3], CITIES.items()):
        with col:
            w = lay_thoi_tiet(info["lat"], info["lon"])
            st.markdown(f"**{info['icon']}**")
            st.markdown(f"**{city}**")
            if w["ok"]:
                st.markdown(f"🌡️ **{w['nhiet_do']}°C**")
                st.markdown(w["mo_ta"])
                st.caption(f"💨 {w['gio']} km/h")
            else:
                st.markdown("–")

    st.markdown("---")

    # ── Disclaimer ──────────────────────────
    st.subheader("⚠️ Lưu ý pháp lý")
    st.warning(
        "Thông tin chỉ mang tính **tham khảo**, không thay thế tư vấn "
        "pháp lý chính thức từ luật sư có chuyên môn. Để được tư vấn "
        "chính xác, vui lòng liên hệ **luật sư hoặc cơ quan pháp luật** "
        "có thẩm quyền."
    )
    st.caption("© 2026 · Trợ Lý Pháp Luật AI · Nguồn: Công báo Chính phủ")

# ====================================
# 3. TIÊU ĐỀ TRANG CHÍNH
# ====================================
st.title("⚖️ Trợ Lý Pháp Luật AI")
st.write("Hệ thống RAG tư vấn văn bản pháp luật tự động — có trích dẫn nguồn chính xác.")

# ====================================
# 4. KHỞI TẠO RAG CORE
# ====================================
@st.cache_resource
def init_rag_core():
    embedding_model = SentenceTransformer(MODEL_NAME, device="cpu")
    index = faiss.read_index("legal_index.faiss")
    return embedding_model, index

@st.cache_resource
def load_metadata():
    with open("metadata.json", "r", encoding="utf-8") as f:
        return json.load(f)

try:
    embedding_model, index = init_rag_core()
    metadata_list = load_metadata()
except Exception as e:
    st.error(f"❌ Chưa có dữ liệu. Vui lòng chạy GitHub Actions để cập nhật: {e}")
    st.stop()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.warning("🔒 Thiếu GEMINI_API_KEY trong App Secrets.")
    st.stop()

client = genai.Client(api_key=api_key)

# ====================================
# 5. HÀM TÌM KIẾM VECTOR
# ====================================
def run_vector_search(query: str, top_k: int) -> dict:
    vec = embedding_model.encode([query], normalize_embeddings=True)
    vec = np.array(vec, dtype="float32")
    scores, indices = index.search(vec, top_k)

    chunks, retrieval_scores = [], []
    for score, idx in zip(scores[0], indices[0]):
        if idx != -1 and idx < len(metadata_list):
            m = metadata_list[idx]
            chunks.append(f"[Nguồn: {m.get('file', '')}]: {m.get('text', '')}")
            retrieval_scores.append(float(score))

    return {"chunks": chunks, "scores": retrieval_scores}

# ====================================
# 6. LỊCH SỬ CHAT
# ====================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.markdown("---")
            st.markdown("**📌 Nguồn luật trích dẫn:**")
            for src in msg["sources"]:
                st.markdown(f"- ⚖️ {src}")
        if msg.get("domain"):
            st.caption(f"📂 Lĩnh vực: `{msg['domain'].upper()}`")

# ====================================
# 7. Ô ĐẶT CÂU HỎI
# ====================================
if user_prompt := st.chat_input("💬 Đặt câu hỏi pháp lý tại đây..."):
    st.session_state.chat_history.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("🔍 Đang rà soát kho văn bản luật..."):

            res       = run_vector_search(user_prompt, top_k=TOP_K)
            chunks    = res["chunks"]
            scores    = res["scores"]
            top_score = max(scores) if scores else 0

            if not chunks or top_score < THRESHOLD:
                reply = (
                    "Hệ thống đã rà soát kho dữ liệu hiện tại nhưng không tìm thấy "
                    "điều luật tương ứng để làm căn cứ trả lời câu hỏi của bạn."
                )
                st.markdown(reply)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": reply, "domain": "Ngoài phạm vi", "sources": []}
                )
            else:
                context_str = "\n".join([f"[{i+1}] {c}" for i, c in enumerate(chunks)])
                prompt_to_llm = f"""Bạn là một trợ lý luật sư cao cấp. Hãy xử lý câu hỏi dựa trên tài liệu thực tế sau đây:
1. Nhận diện lĩnh vực luật (domain) của câu hỏi, viết liền không dấu, viết hoa.
2. Trả lời chi tiết, chính xác câu hỏi dựa trên ngữ cảnh cung cấp.
3. Trích xuất tên các file văn bản xuất hiện trong dấu ngoặc vuông làm căn cứ pháp lý.

Ngữ cảnh tài liệu:
{context_str}

Câu hỏi: {user_prompt}

TRẢ VỀ JSON theo cấu trúc sau, tuyệt đối không viết thêm bất kỳ từ nào ngoài JSON:
{{
    "detected_domain": "TEN_LINH_VUC",
    "answer": "Nội dung trả lời chi tiết",
    "legal_sources": ["ten-file-luat-a.txt", "ten-file-b.txt"]
}}"""

                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt_to_llm,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        ),
                    )
                    raw  = response.text.strip().removeprefix("```json").removesuffix("```").strip()
                    data = json.loads(raw)

                    domain  = data.get("detected_domain", "CHƯA_RÕ")
                    answer  = data.get("answer", "")
                    sources = data.get("legal_sources", [])

                    st.markdown(answer)

                    if sources:
                        st.markdown("---")
                        st.markdown("**📌 Nguồn luật trích dẫn:**")
                        for src in sources:
                            st.markdown(f"- ⚖️ {src}")

                    st.caption(
                        f"📂 Lĩnh vực: `{domain.upper()}` · "
                        f"🎯 Độ khớp: `{top_score:.4f}`"
                    )

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": answer,
                        "domain": domain,
                        "sources": sources,
                    })

                except Exception as e:
                    fallback = (
                        "Hệ thống tìm thấy văn bản phù hợp nhưng đang bận xử lý. "
                        "Vui lòng gửi lại câu hỏi sau giây lát!"
                    )
                    st.markdown(fallback)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": fallback, "domain": "", "sources": []}
                    )
