from __future__ import annotations

import base64
import json
import math
from typing import Any

import httpx

from agents.llm import extract_json
from config import settings

API_BASE = "https://api.perplexity.ai"
ENERGY_DOMAINS = [
    "eia.gov",
    "ferc.gov",
    "pjm.com",
    "ercot.com",
    "caiso.com",
    "fred.stlouisfed.org",
    "opec.org",
    "noaa.gov",
    "reuters.com",
    "bloomberg.com",
]


def is_configured() -> bool:
    return bool(settings.perplexity_api_key)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }


def search_web(query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
    if not is_configured():
        return []
    payload = {
        "query": query,
        "max_results": max_results,
        "search_domain_filter": ENERGY_DOMAINS[:8],
        "search_recency_filter": "week",
    }
    response = httpx.post(f"{API_BASE}/search", headers=_headers(), json=payload, timeout=45.0)
    response.raise_for_status()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": (item.get("snippet") or "")[:400],
            "date": item.get("date"),
        }
        for item in response.json().get("results", [])
    ]


def agent_research(prompt: str, *, instructions: str | None = None) -> dict[str, Any]:
    if not is_configured():
        return {"summary": "", "citations": []}
    payload: dict[str, Any] = {
        "preset": "fast-search",
        "input": prompt,
        "max_output_tokens": 600,
        "stream": False,
    }
    if instructions:
        payload["instructions"] = instructions
    response = httpx.post(f"{API_BASE}/v1/agent", headers=_headers(), json=payload, timeout=60.0)
    response.raise_for_status()
    return _parse_agent_response(response.json())


def _parse_agent_response(data: dict[str, Any]) -> dict[str, Any]:
    summary_parts: list[str] = []
    citations: list[dict[str, str]] = []

    for item in data.get("output", []):
        item_type = item.get("type")
        if item_type == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text" and block.get("text"):
                    summary_parts.append(block["text"])
        elif item_type == "search_results":
            for result in item.get("results", []):
                url = result.get("url", "")
                if url and not any(c["url"] == url for c in citations):
                    citations.append(
                        {
                            "title": result.get("title", url),
                            "url": url,
                            "snippet": (result.get("snippet") or "")[:300],
                        }
                    )

    return {
        "summary": "\n".join(summary_parts).strip(),
        "citations": citations,
        "model": data.get("model"),
    }


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not is_configured() or not texts:
        return []
    payload = {
        "model": "pplx-embed-v1-0.6b",
        "input": texts[:32],
        "encoding_format": "base64_int8",
    }
    response = httpx.post(f"{API_BASE}/v1/embeddings", headers=_headers(), json=payload, timeout=45.0)
    response.raise_for_status()
    vectors: list[list[float]] = []
    for item in sorted(response.json().get("data", []), key=lambda row: row.get("index", 0)):
        raw = base64.b64decode(item.get("embedding", ""))
        vectors.append([float(b) for b in raw])
    return vectors


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def related_by_embedding(query: str, candidates: list[str], *, top_k: int = 3) -> list[dict[str, Any]]:
    if not candidates or not is_configured():
        return []
    texts = [query, *candidates]
    vectors = embed_texts(texts)
    if len(vectors) != len(texts):
        return []
    query_vec = vectors[0]
    scored = [
        (idx, cosine_similarity(query_vec, vec))
        for idx, vec in enumerate(vectors[1:], start=0)
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [
        {"text": candidates[idx], "score": round(score, 3)}
        for idx, score in scored[:top_k]
        if score > 0.2
    ]


def _normalize_verdict(raw: str) -> str:
    text = raw.lower()
    if "challenge" in text or "contradict" in text or "counter" in text:
        return "challenge"
    if "corrobor" in text or "confirm" in text or "support" in text:
        return "corroborate"
    return "mixed"


def _verdict_for_rank(rank: int, title: str, search_hits: list[dict[str, Any]]) -> dict[str, Any]:
    hit_lines = "\n".join(
        f"- {hit.get('title', '')}: {hit.get('snippet', '')[:180]}"
        for hit in search_hits[:3]
    )
    prompt = (
        f"Briefing rank #{rank}: {title}\n\n"
        f"Recent web results:\n{hit_lines or '- No results'}\n\n"
        'Return ONLY JSON: {"verdict":"corroborate|challenge|mixed","summary":"one sentence"}'
    )
    agent = agent_research(
        prompt,
        instructions=(
            "You are an energy market fact-checker. Judge whether web evidence corroborates "
            "or challenges the briefing claim. Be concise."
        ),
    )
    parsed = extract_json(agent.get("summary", ""))
    verdict = "mixed"
    summary = agent.get("summary", "")
    if isinstance(parsed, dict):
        verdict = _normalize_verdict(str(parsed.get("verdict", "mixed")))
        summary = str(parsed.get("summary", summary))
    else:
        verdict = _normalize_verdict(summary)

    citations = [
        {"title": hit.get("title", hit.get("url", "")), "url": hit.get("url", ""), "snippet": hit.get("snippet", "")}
        for hit in search_hits[:3]
        if hit.get("url")
    ]
    for cite in agent.get("citations", []):
        if cite.get("url") and not any(c["url"] == cite["url"] for c in citations):
            citations.append(cite)

    return {
        "rank": rank,
        "title": title,
        "verdict": verdict,
        "summary": summary.split("\n")[0][:300],
        "citations": citations[:4],
    }


def research_briefing(
    *,
    summary: str,
    ranked_items: list[dict[str, Any]],
    signal_summaries: list[str],
) -> dict[str, Any]:
    titles = [str(item.get("title", "")) for item in ranked_items if item.get("title")]
    focus = titles[0] if titles else summary[:200]
    query = (
        f"US energy markets wholesale power natural gas crude oil: {focus}. "
        "Latest news and data from the past week."
    )
    search_results = search_web(query, max_results=6)

    rank_verdicts: list[dict[str, Any]] = []
    for item in ranked_items[:5]:
        rank = int(item.get("rank", len(rank_verdicts) + 1))
        title = str(item.get("title", ""))
        if not title:
            continue
        hits = search_web(f"US energy market: {title}", max_results=4)
        rank_verdicts.append(_verdict_for_rank(rank, title, hits))

    agent_prompt = (
        f"Briefing summary: {summary}\n\n"
        f"Top ranked themes: {'; '.join(titles[:3])}\n\n"
        "In 2-3 sentences, corroborate or challenge this view using current web sources. "
        "Call out contradictions if any."
    )
    agent = agent_research(
        agent_prompt,
        instructions=(
            "You are an energy market research analyst. Be concise and cite specific facts. "
            "Focus on US power, natural gas, and crude oil markets."
        ),
    )

    related = related_by_embedding(summary, signal_summaries[:12], top_k=3)

    return {
        "query": query,
        "search_results": search_results,
        "agent_summary": agent.get("summary", ""),
        "agent_citations": agent.get("citations", []),
        "rank_verdicts": rank_verdicts,
        "related_signals": related,
        "configured": True,
    }
