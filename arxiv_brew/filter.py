"""Two-stage paper filtering: keyword matching + optional LLM refinement.

Stage 2 functions (build_refinement_prompt, parse_refinement_response,
apply_refinement) are not called by any built-in routine. They provide
the API for external agents to integrate LLM-based refinement.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .arxiv_api import Paper
from .config import FilterConfig
from .keywords import KeywordDB


def _keyword_in_text(kw: str, text: str, config: FilterConfig) -> bool:
    kw_lower = kw.lower()
    if kw in config.word_boundary_keywords:
        return bool(re.search(r"\b" + re.escape(kw_lower) + r"\b", text))
    return kw_lower in text


def match_clusters(paper: Paper, config: FilterConfig) -> list[str]:
    text = (paper.title + " " + paper.abstract).lower()
    matched: list[str] = []

    for cluster_name, keywords in config.topic_clusters.items():
        for kw in keywords:
            if not _keyword_in_text(kw, text, config):
                continue
            if kw.lower() in {b.lower() for b in config.broad_keywords}:
                if not any(ck.lower() in text for ck in config.context_keywords):
                    continue
            matched.append(cluster_name)
            break

    return matched


def keyword_filter(papers: list[Paper], config: FilterConfig,
                   keyword_db: Optional[KeywordDB] = None) -> list[Paper]:
    filtered: list[Paper] = []
    for paper in papers:
        clusters = match_clusters(paper, config)
        if clusters:
            paper.matched_clusters = clusters
            filtered.append(paper)
            if keyword_db:
                text = (paper.title + " " + paper.abstract).lower()
                for cluster in clusters:
                    for kw in config.topic_clusters.get(cluster, []):
                        if _keyword_in_text(kw, text, config):
                            keyword_db.record_hit(cluster, kw)
                            break
    return filtered


# --- Stage 2: LLM refinement (called by agents, not by built-in routines) ---

def build_refinement_prompt(
    candidates: list[Paper],
    research_context: str = "",
) -> str:
    parts = [
        "You are a research paper filter.",
        "Judge which candidates are relevant and suggest new keywords.",
        "",
    ]
    if research_context:
        parts.extend(["## Researcher's Background", research_context, ""])
    parts.append("## Candidate Papers\n")

    for i, p in enumerate(candidates, 1):
        clusters = ", ".join(p.matched_clusters) if p.matched_clusters else "none"
        parts.extend([
            f"### [{i}] {p.title}",
            f"arXiv: {p.id} | Clusters: {clusters}",
            f"Authors: {', '.join(p.authors[:5])}{'...' if len(p.authors) > 5 else ''}",
            f"Abstract: {p.abstract[:500]}{'...' if len(p.abstract) > 500 else ''}",
            "",
        ])

    parts.extend([
        "## Response Format",
        "",
        "Decisions (JSON array):",
        '```json\n[{"index": 1, "keep": true, "reason": "..."}]\n```',
        "",
        "New keywords (JSON object):",
        '```json\n{"new_keywords": [{"keyword": "...", "cluster": "...", "reason": "..."}]}\n```',
    ])

    return "\n".join(parts)


def parse_refinement_response(response: str) -> tuple[list[dict], list[dict]]:
    """Parse LLM response into (decisions, new_keywords)."""
    decisions = []
    new_keywords = []

    json_blocks = re.findall(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", response)
    if not json_blocks:
        json_blocks = re.findall(r"(\[[\s\S]*?\])", response)

    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if not isinstance(parsed, list):
                continue
            if parsed and "keep" in parsed[0]:
                decisions = parsed
            elif parsed and "keyword" in parsed[0]:
                new_keywords = parsed
        except json.JSONDecodeError:
            continue

    kw_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    for block in kw_blocks:
        try:
            parsed = json.loads(block)
            if "new_keywords" in parsed:
                new_keywords = parsed["new_keywords"]
        except json.JSONDecodeError:
            continue

    return decisions, new_keywords


def apply_refinement(
    candidates: list[Paper],
    decisions: list[dict],
    new_keywords: list[dict],
    keyword_db: Optional[KeywordDB] = None,
) -> list[Paper]:
    keep_indices = set()
    for d in decisions:
        idx = d.get("index", 0) - 1
        if d.get("keep", False) and 0 <= idx < len(candidates):
            keep_indices.add(idx)

    filtered = [candidates[i] for i in sorted(keep_indices)]

    if keyword_db and new_keywords:
        added = keyword_db.learn_keywords(new_keywords)
        if added:
            keyword_db.save()

    return filtered
