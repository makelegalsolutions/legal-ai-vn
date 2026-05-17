import os
import json
import uuid
from typing import Dict, List
from pathlib import Path

import google.generativeai as genai

# ====================== FIX IMPORT ======================
# Dùng relative import để chạy trên Streamlit Cloud
try:
    from .search_pipeline import legal_search
except ImportError:
    # Fallback cho trường hợp chạy local hoặc test
    from search_pipeline import legal_search
# =======================================================

# ========================================
# CONFIG
# ========================================
MODEL_NAME = "gemini-2.5-flash"          # Hoặc gemini-1.5-pro
MAX_CONTEXT_CHARS = 12000
DEFAULT_TOP_K = 6
DEFAULT_THRESHOLD = 0.45
TEMPERATURE = 0.1

# ========================================
# LOAD API KEY từ config
# ========================================
try:
    from .config import GEMINI_API_KEY
except ImportError:
    try:
        from config import GEMINI_API_KEY
    except ImportError:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise EnvironmentError(
        "❌ GEMINI_API_KEY chưa được thiết lập.\n"
        "Vui lòng kiểm tra file .env hoặc Settings → Secrets trên Streamlit Cloud."
    )

genai.configure(api_key=GEMINI_API_KEY)

# ========================================
# INITIALIZE GEMINI MODEL
# ========================================
gemini_model = genai.GenerativeModel(
    model_name=MODEL_NAME,
    generation_config=genai.GenerationConfig(
        temperature=TEMPERATURE,
        response_mime_type="application/json",
    ),
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
)

print(f"✅ Gemini initialized | Model: {MODEL_NAME}")

# ========================================
# SYSTEM PROMPT
# ========================================
SYSTEM_PROMPT = """
Bạn là trợ lý AI chuyên về pháp luật Việt Nam, trung thực và cẩn thận.

NGUYÊN TẮC BẮT BUỘC:
- Chỉ trả lời dựa trên CONTEXT được cung cấp.
- Không tự suy diễn, không bịa thông tin, không bổ sung kiến thức ngoài CONTEXT.
- Nếu CONTEXT không đủ → phải nói rõ.
- Trích dẫn chính xác số Điều, Khoản, văn bản.
- Viết ngắn gọn, rõ ràng, dễ hiểu cho người dân.
- Không đưa ra lời khuyên pháp lý tuyệt đối.

Hãy trả về JSON hợp lệ theo format sau:
{
  "answer": "Câu trả lời chính",
  "legal_basis": "Trích dẫn cụ thể các điều khoản",
  "note": "Lưu ý quan trọng hoặc hạn chế"
}
"""

# ========================================
# HELPER FUNCTIONS
# ========================================
def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())


def build_context(results: List[Dict]) -> str:
    seen = set()
    blocks = []
    current_length = 0

    for r in results:
        text = clean_text(r.get("text", ""))
        if not text or text in seen:
            continue
        seen.add(text)

        block = f"""[VĂN BẢN PHÁP LUẬT]
Tiêu đề : {r.get('title', 'Không rõ')}
Điều    : {r.get('article', 'Không rõ')}
Văn bản : {r.get('doc_id', 'Không rõ')}
Score   : {r.get('score', 0):.4f}

Nội dung:
{text}
""".strip()

        if current_length + len(block) > MAX_CONTEXT_CHARS:
            break

        blocks.append(block)
        current_length += len(block)

    return "\n\n" + ("\n\n" + "─" * 60 + "\n\n").join(blocks)


def build_citations(results: List[Dict]) -> str:
    citations = []
    seen = set()
    for r in results:
        key = (r.get("article"), r.get("title"))
        if key in seen or not r.get("article"):
            continue
        seen.add(key)
        citations.append(f"• {r.get('article')} | {r.get('title', '')}")
    return "\n".join(citations)


def safe_parse_json(text: str) -> Dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except:
        cleaned = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except:
            return {"answer": text, "legal_basis": "", "note": "Lỗi parse JSON"}


# ========================================
# MAIN FUNCTION
# ========================================
def ask_legal_ai(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    temperature: float = TEMPERATURE,
    debug: bool = False
) -> Dict:
    """Hàm chính: Hỏi đáp pháp luật Việt Nam"""
    
    request_id = uuid.uuid4().hex[:8]
    print(f"\n[#{request_id}] {query}")

    # 1. Retrieval
    retrieval = legal_search(
        query=query,
        top_k=top_k,
        threshold=threshold,
        return_full_text=True
    )

    if retrieval["status"] != "ok":
        return {
            "request_id": request_id,
            "status": retrieval["status"],
            "answer": retrieval.get("message", "Không tìm thấy thông tin phù hợp."),
            "legal_basis": "",
            "note": "",
            "citations": [],
            "retrieved_chunks": []
        }

    # 2. Build context
    results = retrieval["results"]
    context = build_context(results)
    citations = build_citations(results)

    if not context.strip():
        return {
            "request_id": request_id,
            "status": "no_context",
            "answer": "Hiện tại hệ thống chưa có đủ dữ liệu pháp lý để trả lời câu hỏi này.",
            "legal_basis": "",
            "note": "",
            "citations": citations,
            "retrieved_chunks": results
        }

    # 3. Build full prompt
    full_prompt = f"""{SYSTEM_PROMPT}

[CÂU HỎI]
{query}

[CONTEXT]
{context}

Hãy trả lời bằng tiếng Việt, ngắn gọn, chính xác và tuân thủ nghiêm ngặt các nguyên tắc trên."""

    # 4. Call Gemini
    try:
        response = gemini_model.generate_content(full_prompt)
        raw_output = response.text.strip()
        parsed = safe_parse_json(raw_output)
    except Exception as e:
        return {
            "request_id": request_id,
            "status": "llm_error",
            "answer": f"Lỗi khi gọi mô hình: {str(e)}",
            "legal_basis": "",
            "note": "",
            "citations": citations,
            "retrieved_chunks": results
        }

    # 5. Final output
    answer = parsed.get("answer", "Không có câu trả lời.").strip()
    legal_basis = parsed.get("legal_basis", "").strip()
    note = parsed.get("note", "").strip()

    final_answer = f"{answer}\n\n━━━━━━━━━━━━━━━━━━\nCĂN CỨ PHÁP LÝ\n━━━━━━━━━━━━━━━━━━\n\n{citations or 'Không có trích dẫn cụ thể.'}"

    if legal_basis:
        final_answer += f"\n\n━━━━━━━━━━━━━━━━━━\nPHÂN TÍCH\n━━━━━━━━━━━━━━━━━━\n\n{legal_basis}"

    final_answer += f"\n\n━━━━━━━━━━━━━━━━━━\nLƯU Ý\n━━━━━━━━━━━━━━━━━━\n\n{note or 'Thông tin mang tính tham khảo. Khuyến nghị tham khảo ý kiến luật sư hoặc cơ quan nhà nước có thẩm quyền.'}"

    return {
        "request_id": request_id,
        "status": "ok",
        "answer": final_answer.strip(),
        "legal_basis": legal_basis,
        "note": note,
        "citations": citations,
        "retrieved_chunks": results,
        "retrieval_scores": [r.get("score", 0) for r in results]
    }


# ========================================
# TEST
# ========================================
if __name__ == "__main__":
    print("=" * 80)
    print("⚖️  LEGAL AI - GEMINI TEST")
    print("=" * 80)

    test_queries = [
        "Điều kiện để thành lập công ty TNHH là gì?",
        "Thời hạn khiếu nại quyết định hành chính là bao lâu?",
        "Người lao động nữ được nghỉ thai sản bao nhiêu tháng?"
    ]

    for q in test_queries:
        result = ask_legal_ai(q, top_k=5, debug=False)
        print(f"\n❓ Câu hỏi: {q}")
        print(f"📌 Trạng thái: {result['status']}")
        print(f"📝 Trả lời:\n{result['answer'][:800]}...\n")
