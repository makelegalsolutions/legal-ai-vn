import os
import sys
from pathlib import Path
from datetime import datetime

print("=" * 80)
print("🚀 LEGAL AI VN - FULL PIPELINE")
print(f"⏰ Bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

# Đảm bảo chạy từ folder pipeline
os.chdir(Path(__file__).parent)

steps = [
    ("1. Validate Pipeline", "validate_pipeline.py"),
    ("2. Text Processing",   "text_processing.py"),
    ("3. Chunking",          "chunking_pipeline.py"),
    ("4. Vector Embedding",  "vector_pipeline.py"),
    ("5. Search",            "search_pipeline.py"),      # Test search
    ("6. LLM",               "llm_pipeline.py"),         # Test LLM
    ("7. Evaluation",        "evaluation.py"),
]

success_count = 0

for step_name, script in steps:
    print(f"\n🔄 Đang chạy: {step_name}")
    print("-" * 60)
    
    if not os.path.exists(script):
        print(f"❌ Không tìm thấy {script}")
        break
    
    exit_code = os.system(f"python {script}")
    
    if exit_code == 0:
        print(f"✅ {step_name} HOÀN THÀNH")
        success_count += 1
    else:
        print(f"❌ {step_name} BỊ LỖI!")
        break

print("\n" + "="*80)
if success_count == len(steps):
    print("🎉 TOÀN BỘ PIPELINE CHẠY THÀNH CÔNG!")
else:
    print(f"⚠️  Pipeline dừng sau {success_count}/{len(steps)} bước")
print("="*80)
