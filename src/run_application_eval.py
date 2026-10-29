"""Unified Application-Level Evaluation Runner for Pocket AI Lab.

Supports:
- coding: Python syntax, sandboxed unit test execution, SQL query clauses
- structured: JSON schema validation, type checking, negative controls
- tool_calling: Tool selection accuracy, arguments parsing, false-positive prevention
- retrieval: Semantic ranking, Recall@1, Recall@5, MRR via embedding model
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.benchmark import validate_loopback_url
from src.coding_evaluator import evaluate_coding_task
from src.embedding_evaluator import (
    compute_aggregate_retrieval_metrics,
    evaluate_retrieval_ranking,
    get_ollama_embedding,
)
from src.schema import compute_wilson_score_interval
from src.structured_evaluator import evaluate_structured_extraction
from src.tool_calling_evaluator import evaluate_tool_calling


def query_ollama(
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    api_base: str = "http://127.0.0.1:11434",
    temperature: float = 0.0,
    num_ctx: int = 2048,
    timeout: float = 60.0,
) -> Tuple[str, float]:
    """Execute single inference query to local Ollama daemon."""
    validate_loopback_url(api_base)
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": 512,
        },
    }
    if system_prompt:
        payload["system"] = system_prompt

    t0 = time.perf_counter()
    resp = requests.post(f"{api_base}/api/generate", json=payload, timeout=timeout)
    resp.raise_for_status()
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return resp.json().get("response", ""), duration_ms


def run_coding_benchmark(
    model: str,
    dataset_path: str = "datasets/coding_eval_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
) -> Dict[str, Any]:
    """Evaluate model on Python algorithms, bug fixes, and SQL generation."""
    print(f"\n[Eval] Running Coding Benchmark on model '{model}'...", flush=True)
    with open(dataset_path, "r", encoding="utf-8") as f:
        tasks = [json.loads(line) for line in f if line.strip()]

    records = []
    passed_count = 0

    for idx, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        prompt = task["prompt"]
        category = task.get("category", "")
        system = "You are an expert software engineer. Provide exact and functional code."

        print(f"  [{idx}/{len(tasks)}] Task {task_id} ({category})...", end="", flush=True)
        try:
            resp, dur_ms = query_ollama(model, prompt, system_prompt=system, api_base=api_base)
            passed, notes, details = evaluate_coding_task(resp, task)
            status_str = "✔ PASS" if passed else "✘ FAIL"
            print(f" {status_str} ({dur_ms}ms) - {notes}", flush=True)
            if passed:
                passed_count += 1
            records.append({
                "task_id": task_id,
                "category": category,
                "passed": passed,
                "notes": notes,
                "duration_ms": dur_ms,
                "response_text": resp,
                "details": details,
            })
        except Exception as exc:
            print(f" ERROR: {exc}", flush=True)
            records.append({
                "task_id": task_id,
                "category": category,
                "passed": False,
                "notes": str(exc),
                "duration_ms": None,
                "response_text": "",
                "details": {},
            })

    total = len(tasks)
    pass_rate, ci_low, ci_high = compute_wilson_score_interval(passed_count, total)
    summary = {
        "suite": "coding",
        "model": model,
        "total_tasks": total,
        "passed_tasks": passed_count,
        "pass_rate_pct": pass_rate,
        "ci_95_low_pct": ci_low,
        "ci_95_high_pct": ci_high,
        "records": records,
    }
    return summary


def run_structured_benchmark(
    model: str,
    dataset_path: str = "datasets/structured_extraction_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
) -> Dict[str, Any]:
    """Evaluate model on JSON schema, negative controls, and multilingual Hindi/English extraction."""
    print(f"\n[Eval] Running Structured Extraction Benchmark on model '{model}'...", flush=True)
    with open(dataset_path, "r", encoding="utf-8") as f:
        tasks = [json.loads(line) for line in f if line.strip()]

    records = []
    passed_count = 0

    for idx, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        prompt = task["prompt"]
        category = task.get("category", "")
        system = "You are a structured data extraction engine. Return strictly valid JSON."

        print(f"  [{idx}/{len(tasks)}] Task {task_id} ({category})...", end="", flush=True)
        try:
            resp, dur_ms = query_ollama(model, prompt, system_prompt=system, api_base=api_base)
            passed, notes, details = evaluate_structured_extraction(resp, task)
            status_str = "✔ PASS" if passed else "✘ FAIL"
            print(f" {status_str} ({dur_ms}ms) - {notes}", flush=True)
            if passed:
                passed_count += 1
            records.append({
                "task_id": task_id,
                "category": category,
                "passed": passed,
                "notes": notes,
                "duration_ms": dur_ms,
                "response_text": resp,
                "details": details,
            })
        except Exception as exc:
            print(f" ERROR: {exc}", flush=True)
            records.append({
                "task_id": task_id,
                "category": category,
                "passed": False,
                "notes": str(exc),
                "duration_ms": None,
                "response_text": "",
                "details": {},
            })

    total = len(tasks)
    pass_rate, ci_low, ci_high = compute_wilson_score_interval(passed_count, total)
    summary = {
        "suite": "structured",
        "model": model,
        "total_tasks": total,
        "passed_tasks": passed_count,
        "pass_rate_pct": pass_rate,
        "ci_95_low_pct": ci_low,
        "ci_95_high_pct": ci_high,
        "records": records,
    }
    return summary


def run_tool_calling_benchmark(
    model: str,
    dataset_path: str = "datasets/tool_calling_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
) -> Dict[str, Any]:
    """Evaluate model on function selection, argument validity, and false positives."""
    print(f"\n[Eval] Running Tool Calling Benchmark on model '{model}'...", flush=True)
    with open(dataset_path, "r", encoding="utf-8") as f:
        tasks = [json.loads(line) for line in f if line.strip()]

    records = []
    passed_count = 0

    for idx, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        tools_desc = json.dumps(task["candidate_tools"], indent=2)
        user_query = task["user_query"]
        prompt = (
            f"Available tools:\n{tools_desc}\n\n"
            f"User query: '{user_query}'\n\n"
            f"If an external tool is required, call it by outputting JSON: {{\"name\": \"<tool_name>\", \"arguments\": {{...}}}}.\n"
            f"If no tool is required, answer the user query directly without outputting a tool call JSON."
        )

        print(f"  [{idx}/{len(tasks)}] Task {task_id}...", end="", flush=True)
        try:
            resp, dur_ms = query_ollama(model, prompt, api_base=api_base)
            passed, notes, details = evaluate_tool_calling(resp, task)
            status_str = "✔ PASS" if passed else "✘ FAIL"
            print(f" {status_str} ({dur_ms}ms) - {notes}", flush=True)
            if passed:
                passed_count += 1
            records.append({
                "task_id": task_id,
                "passed": passed,
                "notes": notes,
                "duration_ms": dur_ms,
                "response_text": resp,
                "details": details,
            })
        except Exception as exc:
            print(f" ERROR: {exc}", flush=True)
            records.append({
                "task_id": task_id,
                "passed": False,
                "notes": str(exc),
                "duration_ms": None,
                "response_text": "",
                "details": {},
            })

    total = len(tasks)
    pass_rate, ci_low, ci_high = compute_wilson_score_interval(passed_count, total)
    summary = {
        "suite": "tool_calling",
        "model": model,
        "total_tasks": total,
        "passed_tasks": passed_count,
        "pass_rate_pct": pass_rate,
        "ci_95_low_pct": ci_low,
        "ci_95_high_pct": ci_high,
        "records": records,
    }
    return summary


def run_retrieval_benchmark(
    embedding_model: str = "nomic-embed-text",
    dataset_path: str = "datasets/retrieval_eval_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
) -> Dict[str, Any]:
    """Evaluate embedding model on offline semantic retrieval (Recall@1, Recall@5, MRR)."""
    print(f"\n[Eval] Running Semantic Retrieval Benchmark using embedding model '{embedding_model}'...", flush=True)
    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    corpus_entry = next((l for l in lines if l.get("type") == "corpus"), None)
    queries = [l for l in lines if l.get("type") == "query"]
    if not corpus_entry or not queries:
        raise ValueError("Invalid retrieval dataset: missing corpus or queries")

    passages = corpus_entry.get("passages", [])
    print(f"  Embedding {len(passages)} corpus passages...", flush=True)
    corpus_vectors: Dict[str, List[float]] = {}
    embed_latencies = []

    for p in passages:
        doc_id = p["id"]
        text = p["text"]
        vec, dur_ms = get_ollama_embedding(text, model=embedding_model, api_base=api_base)
        if vec is not None:
            corpus_vectors[doc_id] = vec
            embed_latencies.append(dur_ms)
        else:
            print(f"    Failed to embed {doc_id}")

    if not corpus_vectors:
        return {"suite": "retrieval", "status": "error", "message": f"Embedding model '{embedding_model}' not available in Ollama"}

    print(f"  Evaluating {len(queries)} retrieval queries...", flush=True)
    query_eval_results = []
    for q in queries:
        q_id = q["query_id"]
        q_text = q["query"]
        relevant_docs = q["relevant_doc_ids"]

        q_vec, dur_ms = get_ollama_embedding(q_text, model=embedding_model, api_base=api_base)
        if q_vec is None:
            continue
        embed_latencies.append(dur_ms)

        ranking_res = evaluate_retrieval_ranking(q_vec, corpus_vectors, relevant_docs)
        ranking_res["query_id"] = q_id
        query_eval_results.append(ranking_res)

    aggregate = compute_aggregate_retrieval_metrics(query_eval_results)
    avg_latency = round(sum(embed_latencies) / len(embed_latencies), 2) if embed_latencies else 0.0

    print("\n" + "=" * 60)
    print(f" RETRIEVAL BENCHMARK RESULTS: {embedding_model}")
    print("=" * 60)
    print(f"  Recall@1 : {aggregate['recall_at_1_pct']}%")
    print(f"  Recall@5 : {aggregate['recall_at_5_pct']}%")
    print(f"  MRR      : {aggregate['mrr']}")
    print(f"  Avg Embed Latency: {avg_latency} ms")
    print("=" * 60 + "\n")

    return {
        "suite": "retrieval",
        "embedding_model": embedding_model,
        "total_queries": len(queries),
        "recall_at_1_pct": aggregate["recall_at_1_pct"],
        "recall_at_5_pct": aggregate["recall_at_5_pct"],
        "mrr": aggregate["mrr"],
        "avg_embed_latency_ms": avg_latency,
        "query_results": query_eval_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run application-level evaluations")
    parser.add_argument("--suite", type=str, required=True, choices=["coding", "structured", "tool_calling", "retrieval", "all"])
    parser.add_argument("--model", type=str, default="qwen2.5:1.5b")
    parser.add_argument("--embedding-model", type=str, default="nomic-embed-text")
    parser.add_argument("--api-base", type=str, default="http://127.0.0.1:11434")
    parser.add_argument("--output-dir", type=str, default="results")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    clean_m = re.sub(r"[^a-zA-Z0-9_-]", "_", args.model)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

    results: Dict[str, Any] = {}
    if args.suite in ["coding", "all"]:
        results["coding"] = run_coding_benchmark(args.model, api_base=args.api_base)
    if args.suite in ["structured", "all"]:
        results["structured"] = run_structured_benchmark(args.model, api_base=args.api_base)
    if args.suite in ["tool_calling", "all"]:
        results["tool_calling"] = run_tool_calling_benchmark(args.model, api_base=args.api_base)
    if args.suite in ["retrieval", "all"]:
        results["retrieval"] = run_retrieval_benchmark(args.embedding_model, api_base=args.api_base)

    out_file = os.path.join(args.output_dir, f"app_eval_{args.suite}_{clean_m}_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[Eval] Complete results saved to {out_file}")


if __name__ == "__main__":
    main()
