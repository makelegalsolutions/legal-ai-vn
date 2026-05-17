import os
from pathlib import Path
from dotenv import load_dotenv

# ========================================
# LOAD .env FILE (ưu tiên)
# ========================================
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ========================================
# API KEYS
# ========================================

# Gemini (Google)
GEMINI_API_KEY = os.getenv("AIzaSyBADYaZOrCLKBOb6AH-WjYZuHTBSHPHMpg")

# OpenAI (nếu sau này dùng)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Groq (tùy chọn)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ========================================
# VALIDATION & WARNING
# ========================================

def check_api_keys():
    print("=" * 60)
    print("🔑 API KEY CONFIGURATION")
    print("=" * 60)

    if GEMINI_API_KEY:
        print(f"✅ GEMINI_API_KEY: Đã thiết lập ({GEMINI_API_KEY[:8]}...)")
    else:
        print("❌ GEMINI_API_KEY: Chưa có!")
        print("   → Vui lòng tạo file .env hoặc set biến môi trường")

    if OPENAI_API_KEY:
        print(f"✅ OPENAI_API_KEY : Đã thiết lập")
    if GROQ_API_KEY:
        print(f"✅ GROQ_API_KEY    : Đã thiết lập")

    print("=" * 60)


# ========================================
# AUTO SET FOR NOTEBOOK / SCRIPT
# ========================================
if not GEMINI_API_KEY:
    print("⚠️  GEMINI_API_KEY chưa được thiết lập.")
    print("   Bạn có thể set thủ công bằng cách chạy:")
    print("   os.environ['GEMINI_API_KEY'] = 'your_key_here'")

# Run check when imported
if __name__ == "__main__":
    check_api_keys()
else:
    # Khi import vào các file khác
    check_api_keys()
