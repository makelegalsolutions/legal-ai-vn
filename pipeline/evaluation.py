import json
import time
import pandas as pd
from datetime import datetime
from pathlib import Path

# Import từ các pipeline trước
from llm_pipeline import ask_legal_ai

# ========================================
# CONFIG
# ========================================
EVAL_RESULTS_DIR = "data/evaluation"
Path(EVAL_RESULTS_DIR).mkdir(parents=True, exist_ok=True)

# ========================================
# TEST SET (có thể mở rộng sau)
# ========================================
EVAL_SET = [
    {
        "query": "Điều kiện thành lập doanh nghiệp là gì?",
        "expected_domain": "Doanh nghiệp",
    },
    {
        "query": "Công ty phá sản thì người lao động được xử lý lương thế nào?",
        "expected_domain": "Phá sản",
    },
    {
        "query": "Điều kiện mở công ty trách nhiệm hữu hạn",
        "expected_domain": "Doanh nghiệp",
    },
    {
        "query": "Nghỉ thai sản được bao nhiêu tháng?",
        "expected_domain": None,           # Out-of-scope hoặc chưa có dữ liệu
    },
    {
        "query": "Không đội mũ bảo hiểm bị phạt bao nhiêu?",
        "expected_domain": None,
    },
    {
        "query": "Thời hạn khiếu nại quyết định hành chính là bao lâu?",
        "expected_domain": "Khiếu nại",
    },
]

# ========================================
# DOMAIN NORMALIZATION
# ========================================
def safe_normalize_domain(domain):
    if domain is None:
        return None
    if not isinstance(domain, str):
        return str(domain).strip().lower()
    return domain.strip().lower().replace(" ", "_")


# ========================================
# MAIN EVALUATION FUNCTION
# ========================================
def evaluate_legal_ai(
    eval_set=EVAL_SET,
    top_k: int = 5,
    threshold: float = 0.4,
    save_results: bool = True
):
    rows = []
    raw_logs = []

    print("\n" + "=" * 90)
    print("⚖️  LEGAL AI - EVALUATION")
    print("=" * 90)

    for i, sample in enumerate(eval_set, 1):
        query = sample["query"]
        expected_domain = sample.get("expected_domain")

        print(f"\n[{i:2d}/{len(eval_set)}] {query}")

        try:
            start_time = time.time()

            result = ask_legal_ai(
                query=query,
                top_k=top_k,
                threshold=threshold,
                debug=True
            )

            latency_sec = round(time.time() - start_time, 2)

            # Extract metrics
            status = result.get("status")
            predicted_domain = result.get("best_domain")
            retrieval_scores = result.get("retrieval_scores") or []
            top_score = max(retrieval_scores) if retrieval_scores else 0.0
            num_chunks = len(result.get("retrieved_chunks", []))

            answer_text = result.get("answer", "")
            answer_length = len(answer_text)
            answer_preview = answer_text[:300].replace("\n", " ") if answer_text else ""

            # Domain correctness
            normalized_expected = safe_normalize_domain(expected_domain)
            normalized_predicted = safe_normalize_domain(predicted_domain)

            if normalized_expected is None:
                domain_correct = status in ("out_of_scope", "no_result", "no_context")
            else:
                domain_correct = (status == "ok") and (normalized_predicted == normalized_expected)

            # Hallucination flag
            hallucination_flag = (status == "ok") and (num_chunks == 0 or top_score < 0.5)

            # Save row
            row = {
                "query": query,
                "status": status,
                "expected_domain": expected_domain,
                "predicted_domain": predicted_domain,
                "normalized_expected": normalized_expected,
                "normalized_predicted": normalized_predicted,
                "domain_correct": domain_correct,
                "top_score": round(float(top_score), 4),
                "num_chunks": num_chunks,
                "answer_length": answer_length,
                "latency_sec": latency_sec,
                "hallucination_flag": hallucination_flag,
                "answer_preview": answer_preview,
                "request_id": result.get("request_id")
            }

            rows.append(row)
            raw_logs.append({"query": query, "request_id": result.get("request_id"), "result": result})

            # Console log
            icon = "✅" if domain_correct else "❌"
            print(f"   Status       : {status}")
            print(f"   Domain       : {normalized_predicted} (expected: {normalized_expected}) {icon}")
            print(f"   Top Score    : {top_score:.4f}")
            print(f"   Chunks       : {num_chunks}")
            print(f"   Latency      : {latency_sec}s")
            if hallucination_flag:
                print("   ⚠️  Possible Hallucination")

        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            rows.append({
                "query": query,
                "status": "error",
                "expected_domain": expected_domain,
                "predicted_domain": None,
                "normalized_expected": None,
                "normalized_predicted": None,
                "domain_correct": False,
                "top_score": 0,
                "num_chunks": 0,
                "answer_length": 0,
                "latency_sec": 0,
                "hallucination_flag": False,
                "answer_preview": str(e),
                "request_id": None
            })

        print("-" * 90)

    # ========================================
    # SUMMARY
    # ========================================
    df = pd.DataFrame(rows)

    total = len(df)
    success = (df["status"] == "ok").sum()
    oos_total = df["expected_domain"].isna().sum()
    oos_correct = ((df["expected_domain"].isna()) & (df["domain_correct"])).sum()

    print("\n" + "=" * 90)
    print("📊 EVALUATION SUMMARY")
    print("=" * 90)
    print(f"Total cases             : {total}")
    print(f"Successful (ok)         : {success}")
    print(f"Domain Accuracy         : {df['domain_correct'].mean():.2%}")
    print(f"Out-of-scope correct    : {oos_correct}/{oos_total}")
    print(f"Retrieval pass rate     : {(df['num_chunks'] > 0).mean():.2%}")
    print(f"Hallucination rate      : {df['hallucination_flag'].mean():.2%}")
    print(f"Avg Top Score           : {df['top_score'].mean():.4f}")
    print(f"Avg Latency             : {df['latency_sec'].mean():.2f}s")

    # ========================================
    # SAVE RESULTS
    # ========================================
    if save_results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        csv_file = Path(EVAL_RESULTS_DIR) / f"legal_eval_{timestamp}.csv"
        jsonl_file = Path(EVAL_RESULTS_DIR) / f"legal_eval_raw_{timestamp}.jsonl"

        df.to_csv(csv_file, index=False, encoding="utf-8-sig")
        
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for log in raw_logs:
                f.write(json.dumps(log, ensure_ascii=False) + "\n")

        print(f"\n💾 Saved → {csv_file}")
        print(f"💾 Raw log → {jsonl_file}")

    return df


# ========================================
# RUN EVALUATION
# ========================================
if __name__ == "__main__":
    eval_df = evaluate_legal_ai(
        eval_set=EVAL_SET,
        top_k=5,
        threshold=0.4
    )
    print("\n✅ Evaluation completed!")
    print(eval_df[["query", "status", "domain_correct", "top_score", "latency_sec"]])
