"""Embedding and Retrieval Evaluator for Edge Models.

Evaluates semantic retrieval accuracy:
- Cosine similarity ranking
- Recall@1 and Recall@5
- Mean Reciprocal Rank (MRR)
- Embedding latency (ms) and throughput (embeddings/sec)
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.benchmark import validate_loopback_url


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_ollama_embedding(
    text: str,
    model: str = "nomic-embed-text",
    api_base: str = "http://127.0.0.1:11434",
    timeout: float = 45.0,
) -> Tuple[Optional[List[float]], float]:
    """Retrieve text embedding from Ollama API with timing."""
    validate_loopback_url(api_base)
    t0 = time.perf_counter()

    # Try /api/embeddings (classic)
    try:
        resp = requests.post(
            f"{api_base}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=timeout,
        )
        if resp.status_code == 200:
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            emb = resp.json().get("embedding")
            return emb, duration_ms
    except Exception:
        pass

    # Try /api/embed (newer Ollama)
    try:
        resp = requests.post(
            f"{api_base}/api/embed",
            json={"model": model, "input": text},
            timeout=timeout,
        )
        if resp.status_code == 200:
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            data = resp.json()
            embs = data.get("embeddings", [])
            emb = embs[0] if embs else None
            return emb, duration_ms
    except Exception:
        pass

    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return None, duration_ms


def evaluate_retrieval_ranking(
    query_vector: List[float],
    corpus_vectors: Dict[str, List[float]],
    relevant_doc_ids: List[str],
) -> Dict[str, Any]:
    """Rank corpus passages by cosine similarity and compute Recall@k and MRR."""
    scores: List[Tuple[str, float]] = []
    for doc_id, doc_vec in corpus_vectors.items():
        sim = cosine_similarity(query_vector, doc_vec)
        scores.append((doc_id, sim))

    # Sort descending by score
    scores.sort(key=lambda x: x[1], reverse=True)
    ranked_doc_ids = [s[0] for s in scores]

    # Calculate metrics
    hit_at_1 = any(doc_id in ranked_doc_ids[:1] for doc_id in relevant_doc_ids)
    hit_at_5 = any(doc_id in ranked_doc_ids[:5] for doc_id in relevant_doc_ids)

    # Reciprocal Rank (RR)
    rr = 0.0
    for rank_idx, doc_id in enumerate(ranked_doc_ids, start=1):
        if doc_id in relevant_doc_ids:
            rr = 1.0 / rank_idx
            break

    return {
        "recall_at_1": 1.0 if hit_at_1 else 0.0,
        "recall_at_5": 1.0 if hit_at_5 else 0.0,
        "mrr": round(rr, 4),
        "top_5_results": ranked_doc_ids[:5],
        "top_score": round(scores[0][1], 4) if scores else 0.0,
    }


def compute_aggregate_retrieval_metrics(
    eval_results: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute average Recall@1, Recall@5, and MRR across all queries."""
    if not eval_results:
        return {"recall_at_1_pct": 0.0, "recall_at_5_pct": 0.0, "mrr": 0.0}

    n = len(eval_results)
    avg_r1 = sum(r["recall_at_1"] for r in eval_results) / n * 100.0
    avg_r5 = sum(r["recall_at_5"] for r in eval_results) / n * 100.0
    avg_mrr = sum(r["mrr"] for r in eval_results) / n

    return {
        "recall_at_1_pct": round(avg_r1, 2),
        "recall_at_5_pct": round(avg_r5, 2),
        "mrr": round(avg_mrr, 4),
    }
