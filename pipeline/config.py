import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ========================================
# API KEYS
# ========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # ĐÃ SỬA - không hardcode
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def check_api_keys():
    """Kiểm tra trạng thái API keys - chỉ in ra nếu chạy trực tiếp"""
    print("=" * 60)
    print("🔑 API KEY STATUS")
    print("=" * 60)
    
    if GEMINI_API_KEY:
        masked = GEMINI_API_KEY[:8] + "..." + GEMINI_API_KEY[-4:]
        print(f"✅ GEMINI_API_KEY → {masked}")
    else:
        print("❌ GEMINI_API_KEY: Chưa thiết lập!")
    
    print("=" * 60)

# ĐÃ SỬA: Không tự động chạy check_api_keys() khi import
# Chỉ chạy khi file được thực thi trực tiếp
if __name__ == "__main__":
    check_api_keys()
