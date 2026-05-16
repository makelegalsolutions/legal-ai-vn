import streamlit as st
import requests
import datetime

# ====================================
# SIDEBAR
# ====================================
with st.sidebar:

    # ── Bộ đếm ──────────────────────────────
    # (Dùng file đếm thật nếu muốn persistent,
    #  hiện tại dùng session cho đơn giản)
    st.header("📊 Hệ Thống")
    st.markdown("---")

    # ── Thời gian thực ──────────────────────
    st.subheader("📆 Thời Gian")
    now = datetime.datetime.now()
    st.markdown(f"🕒 **Giờ Hà Nội:** `{now.strftime('%H:%M:%S')}`")
    st.markdown(f"📅 **Dương lịch:** {now.strftime('%d/%m/%Y')}")

    # Lịch âm dùng lunarcalendar
    try:
        from lunarcalendar import Converter, Solar
        lunar = Converter.Solar2Lunar(Solar(now.year, now.month, now.day))
        st.markdown(f"🌙 **Âm lịch:** Ngày {lunar.day} tháng {lunar.month} năm {lunar.year}")
    except ImportError:
        st.markdown(f"🌙 **Âm lịch:** *(cài `lunarcalendar` để hiển thị)*")

    st.markdown("---")

    # ── Thời tiết 3 miền (Open-Meteo, miễn phí, không cần API key) ──
    st.subheader("🌤️ Thời Tiết")

    CITIES = {
        "Hà Nội":   {"lat": 21.0285, "lon": 105.8542, "icon": "🏙️"},
        "Nha Trang":  {"lat": 16.0544, "lon": 108.2022, "icon": "🌊"},
        "TP.HCM":   {"lat": 10.8231, "lon": 106.6297, "icon": "🏢"},
    }

    WEATHER_CODE = {
        0:  "☀️ Quang đãng",
        1:  "🌤️ Ít mây",  2: "⛅ Nhiều mây",  3: "☁️ Âm u",
        45: "🌫️ Sương mù", 48: "🌫️ Sương giá",
        51: "🌦️ Mưa phùn", 53: "🌦️ Mưa phùn", 55: "🌧️ Mưa phùn dày",
        61: "🌧️ Mưa nhẹ",  63: "🌧️ Mưa vừa",  65: "🌧️ Mưa to",
        71: "🌨️ Tuyết nhẹ", 73: "🌨️ Tuyết", 75: "❄️ Tuyết dày",
        80: "🌦️ Mưa rào",  81: "🌧️ Mưa rào",  82: "⛈️ Mưa rào mạnh",
        95: "⛈️ Dông",     96: "⛈️ Dông đá",   99: "⛈️ Dông đá mạnh",
    }

    @st.cache_data(ttl=1800)  # cache 30 phút
    def lay_thoi_tiet(lat: float, lon: float) -> dict:
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weathercode,windspeed_10m"
                f"&timezone=Asia%2FBangkok"
            )
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()["current"]
            return {
                "nhiet_do": round(data["temperature_2m"]),
                "code":     data["weathercode"],
                "gio":      round(data["windspeed_10m"]),
                "ok":       True,
            }
        except Exception:
            return {"ok": False}

    cols = st.columns(3)
    for col, (city, info) in zip(cols, CITIES.items()):
        with col:
            tiet = lay_thoi_tiet(info["lat"], info["lon"])
            mo_ta = WEATHER_CODE.get(tiet.get("code", -1), "–") if tiet["ok"] else "–"
            nhiet = f"{tiet['nhiet_do']}°C" if tiet["ok"] else "–"
            gio   = f"{tiet['gio']} km/h" if tiet["ok"] else ""

            st.markdown(f"**{info['icon']} {city}**")
            st.markdown(f"🌡️ {nhiet}")
            st.markdown(mo_ta)
            if gio:
                st.caption(f"💨 {gio}")

    if not any(lay_thoi_tiet(v["lat"], v["lon"])["ok"] for v in CITIES.values()):
        st.caption("⚠️ Không lấy được dữ liệu thời tiết. Kiểm tra kết nối mạng.")

    st.markdown("---")

    # ── Disclaimer pháp lý ──────────────────
    st.subheader("⚠️ Lưu ý pháp lý")
    st.warning(
        """
        Thông tin do hệ thống cung cấp **chỉ mang tính tham khảo**, 
        không thay thế tư vấn pháp lý chính thức từ luật sư có chuyên môn.

        Để được tư vấn chính xác, vui lòng liên hệ **luật sư hoặc 
        cơ quan pháp luật có thẩm quyền**.
        """
    )
    st.caption("© 2026 · Trợ Lý Pháp Luật AI · Dữ liệu từ Công báo Chính phủ")
