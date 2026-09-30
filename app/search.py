from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
import re
import time
from typing import Literal

from app.config import get_settings
from app.db import get_collection
from app.embeddings import embed_query, rerank_documents


SearchMode = Literal["lexical", "vector", "hybrid"]


def _project(score_meta: str) -> dict:
    return {
        "$project": {
            "_id": {"$toString": "$_id"},
            "source_id": 1,
            "filename": 1,
            "document_title": 1,
            "page": 1,
            "chunk_index": 1,
            "chunk_kind": 1,
            "section_title": 1,
            "text": 1,
            "visual": 1,
            "score": {"$meta": score_meta},
        }
    }


def lexical_stage(query: str, source_id: str) -> dict:
    settings = get_settings()
    return {
        "$search": {
            "index": settings.lexical_index_name,
            "compound": {
                "should": [
                    {
                        "text": {
                            "query": query,
                            "path": "lexical_text",
                            "score": {"boost": {"value": 1.0}},
                        }
                    },
                    {
                        "text": {
                            "query": query,
                            "path": "section_title",
                            "score": {"boost": {"value": 2.0}},
                        }
                    },
                    {
                        "text": {
                            "query": query,
                            "path": ["lexical_text", "section_title"],
                            "fuzzy": {"maxEdits": 1, "prefixLength": 2, "maxExpansions": 32},
                            "score": {"boost": {"value": 0.15}},
                        }
                    },
                ],
                "minimumShouldMatch": 1,
                "filter": [{"equals": {"path": "source_id", "value": source_id}}],
            },
        }
    }


def lexical_search(query: str, source_id: str, limit: int) -> list[dict]:
    return list(
        get_collection().aggregate(
            [lexical_stage(query, source_id), {"$limit": limit}, _project("searchScore")]
        )
    )


def vector_stage(query_vector: list[float], lane_key: str, source_id: str, limit: int) -> dict:
    lane = get_settings().lane(lane_key)
    return {
        "$vectorSearch": {
            "index": lane.index_name,
            "path": lane.field,
            "queryVector": query_vector,
            "exact": True,
            "filter": {"source_id": source_id},
            "limit": limit,
        }
    }


def vector_search(query: str, source_id: str, lane_key: str, limit: int) -> list[dict]:
    query_vector = embed_query(query, lane_key)
    return list(
        get_collection().aggregate(
            [vector_stage(query_vector, lane_key, source_id, limit), _project("vectorSearchScore")]
        )
    )


def _weights() -> tuple[float, float]:
    settings = get_settings()
    total = settings.hybrid_vector_weight + settings.hybrid_lexical_weight
    if total <= 0:
        raise ValueError("Hybrid weights must sum to a positive value")
    return settings.hybrid_vector_weight / total, settings.hybrid_lexical_weight / total


def hybrid_search(query: str, source_id: str, lane_key: str, limit: int) -> list[dict]:
    settings = get_settings()
    query_vector = embed_query(query, lane_key)
    candidate_limit = max(20, limit * 3)
    vector_weight, lexical_weight = _weights()
    pipeline = [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "vectorPipeline": [
                            vector_stage(query_vector, lane_key, source_id, candidate_limit)
                        ],
                        "lexicalPipeline": [
                            lexical_stage(query, source_id),
                            {"$limit": candidate_limit},
                        ],
                    }
                },
                "combination": {
                    "weights": {
                        "vectorPipeline": vector_weight,
                        "lexicalPipeline": lexical_weight,
                    }
                },
                "scoreDetails": True,
            }
        },
        {"$limit": limit},
        _project("scoreDetails"),
    ]
    return list(get_collection().aggregate(pipeline))


def _score_value(score) -> float | None:
    if isinstance(score, (int, float)):
        return float(score)
    if isinstance(score, dict) and isinstance(score.get("value"), (int, float)):
        return float(score["value"])
    return None


def extractive_answer(query: str, results: list[dict], max_sentences: int = 3) -> str:
    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9]{3,}", query)}
    candidates = []
    for result in results[:5]:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", result.get("text", "")):
            clean = sentence.strip()
            if len(clean) < 30:
                continue
            words = {word.lower() for word in re.findall(r"[a-zA-Z0-9]{3,}", clean)}
            overlap = len(terms & words)
            candidates.append((overlap / math.sqrt(max(len(words), 1)), overlap, clean))
    ranked = [sentence for _, overlap, sentence in sorted(candidates, reverse=True) if overlap]
    if not ranked and results:
        ranked = [results[0].get("text", "")]
    return " ".join(ranked[:max_sentences])


def apply_reranker(query: str, results: list[dict], limit: int) -> list[dict]:
    ranked = rerank_documents(
        query,
        [result.get("text", "") for result in results],
        top_k=limit,
    )
    reordered = []
    for item in ranked:
        index = getattr(item, "index", None)
        if index is None and isinstance(item, dict):
            index = item.get("index")
        if not isinstance(index, int) or not 0 <= index < len(results):
            continue
        score = getattr(item, "relevance_score", None)
        if score is None and isinstance(item, dict):
            score = item.get("relevance_score")
        result = dict(results[index])
        result["rerank_score"] = float(score) if isinstance(score, (int, float)) else None
        reordered.append(result)
    return reordered or results[:limit]


def run_pipeline(
    query: str,
    source_id: str,
    mode: SearchMode,
    lane_key: str | None,
    limit: int,
    rerank: bool = False,
) -> dict:
    started = time.perf_counter()
    candidate_limit = max(20, limit * 4) if rerank else limit
    if mode == "lexical":
        results = lexical_search(query, source_id, candidate_limit)
        label = "Atlas Full-Text Search"
        model = "$search"
        representation = "Shared canonical chunks"
    else:
        if not lane_key:
            raise ValueError("A Voyage model is required for vector and hybrid search")
        lane = get_settings().lane(lane_key)
        results = (
            vector_search(query, source_id, lane_key, candidate_limit)
            if mode == "vector"
            else hybrid_search(query, source_id, lane_key, candidate_limit)
        )
        label = lane.label
        model = lane.model
        representation = lane.representation
    rerank_ms = 0.0
    if rerank:
        rerank_started = time.perf_counter()
        results = apply_reranker(query, results, limit)
        rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
    results = results[:limit]
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    for result in results:
        result["score_value"] = _score_value(result.get("score"))
    return {
        "key": lane_key or "atlas_lexical",
        "label": label,
        "model": model,
        "representation": representation,
        "mode": mode,
        "latency_ms": latency_ms,
        "reranked": rerank,
        "rerank_model": get_settings().voyage_rerank_model if rerank else None,
        "rerank_ms": rerank_ms,
        "candidate_count": candidate_limit,
        "answer": extractive_answer(query, results),
        "results": results,
    }


def compare_pipelines(
    query: str,
    source_id: str,
    mode: SearchMode,
    limit: int,
    rerank: bool = False,
) -> list[dict]:
    if mode == "lexical":
        return [run_pipeline(query, source_id, mode, None, limit, rerank)]
    settings = get_settings()
    sample = get_collection().find_one(
        {"source_id": source_id, "record_type": "chunk"},
        {lane.field: 1 for lane in settings.lanes},
    )
    if not sample:
        raise ValueError("The selected PDF was not found")
    lane_keys = [
        lane.key
        for lane in settings.lanes
        if isinstance(sample.get(lane.field), list) and sample[lane.field]
    ]
    if not lane_keys:
        raise ValueError("The selected PDF has no searchable vector model lanes")
    with ThreadPoolExecutor(max_workers=len(lane_keys)) as executor:
        futures = [
            executor.submit(run_pipeline, query, source_id, mode, lane_key, limit, rerank)
            for lane_key in lane_keys
        ]
        return [future.result() for future in futures]
