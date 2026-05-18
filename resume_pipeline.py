#!/usr/bin/env python3
"""
Resume pipeline từ checkpoint hoặc clean start
Chạy: python resume_pipeline.py
"""

import os
import shutil

def clean_for_resume():
    """Xóa file không hoàn chỉnh, giữ checkpoint"""
    print("🧹 Cleaning incomplete files...")
    
    # Giữ lại downloads, texts, chunks
    print("   ✅ Keeping: data/downloads/")
    print("   ✅ Keeping: data/texts/")
    print("   ✅ Keeping: data/chunks/")
    
    # Xóa file embeddings không hoàn chỉnh
    files_to_remove = [
        "data/vectorstore/embeddings.npy",
        "data/vectorstore/legal_index.faiss",
        "data/vectorstore/index_metadata.json",
        "data/vectorstore/chunks_metadata.json",
    ]
    
    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print(f"   🗑️ Deleted: {f}")
    
    # Kiểm tra checkpoint
    checkpoint = "data/vectorstore/embeddings_checkpoint.npz"
    if os.path.exists(checkpoint):
        print(f"   💾 Checkpoint exists: {checkpoint}")
        print("   ✅ Will resume from checkpoint")
    else:
        print("   ⚠️ No checkpoint found, will start from beginning")

def clean_all():
    """Xóa tất cả, chạy từ đầu"""
    print("🔥 Cleaning ALL data...")
    
    dirs_to_remove = [
        "data/texts",
        "data/chunks", 
        "data/vectorstore",
    ]
    
    for d in dirs_to_remove:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"   🗑️ Removed: {d}/")
        os.makedirs(d, exist_ok=True)
        print(f"   📁 Created: {d}/")

if __name__ == "__main__":
    print("=" * 50)
    print("RESUME PIPELINE")
    print("=" * 50)
    print("1. Resume from checkpoint (recommended)")
    print("2. Clean all and start fresh")
    print("3. Cancel")
    
    choice = input("\nChoose (1/2/3): ")
    
    if choice == "1":
        clean_for_resume()
        print("\n✅ Ready to resume!")
        print("Run: python pipeline/vector_pipeline.py")
    elif choice == "2":
        confirm = input("Type CONFIRM to delete all: ")
        if confirm == "CONFIRM":
            clean_all()
            print("\n✅ Ready for fresh start!")
            print("Run: python pipeline/validate_pipeline.py")
        else:
            print("Cancelled")
    else:
        print("Cancelled")
