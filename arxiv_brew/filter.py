"""
Two-stage paper filtering engine.

Stage 1 (keyword): Fast local matching against keyword DB → broad candidate set
Stage 2 (LLM refine): LLM judges relevance of candidates → final set + keyword learning

Stage 2 is optional — when no LLM is available, stage 1 output is used directly.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .arxiv_api import Paper
from .config import FilterConfig
from .keywords import KeywordDB


# ── Stage 1: Keyword matching ──

def _keyword_in_text(kw: str, text: str, config: FilterConfig) -> bool:
    """Check keyword presence with appropriate matching strategy."""
    kw_lower = kw.lower()
    if kw in config.word_boundary_keywords:
        return bool(re.search(r"\b" + re.escape(kw_lower) + r"\b", text))
    return kw_lower in text


def match_clusters(paper: Paper, config: FilterConfig) -> list[str]:
    """Return matching cluster names for a paper (stage 1)."""
    text = (paper.title + " " + paper.abstract).lower()
    matched: list[str] = []

    for cluster_name, keywords in config.topic_clusters.items():
        for kw in keywords:
            if not _keyword_in_text(kw, text, config):
                continue
            if kw.lower() in {b.lower() for b in config.broad_keywords}:
                has_context = any(ck.lower() in text for ck in config.context_keywords)
                if not has_context:
                    continue
            matched.append(cluster_name)
            break

    return matched


def keyword_filter(papers: list[Paper], config: FilterConfig,
                   keyword_db: Optional[KeywordDB] = None) -> list[Paper]:
    """Stage 1: keyword-based filtering. Populates paper.matched_clusters.
    
    Also records hits in keyword_db if provided.
    """
    filtered: list[Paper] = []
    for paper in papers:
        clusters = match_clusters(paper, config)
        if clusters:
            paper.matched_clusters = clusters
            filtered.append(paper)

            # Record which keywords hit
            if keyword_db:
                text = (paper.title + " " + paper.abstract).lower()
                for cluster in clusters:
                    for kw in config.topic_clusters.get(cluster, []):
                        if _keyword_in_text(kw, text, config):
                            keyword_db.record_hit(cluster, kw)
                            break

    return filtered


# ── Stage 2: LLM refinement ──

def build_refinement_prompt(
    candidates: list[Paper],
    research_context: str = "",
) -> str:
    """Build the prompt for LLM stage-2 refinement.
    
    The LLM should:
    1. Judge each candidate's relevance (keep/drop)
    2. Suggest new keywords for future matching
    
    Returns a prompt string.
    """
    prompt_parts = [
        "You are a research paper filter for a computational physics researcher.",
        "Your job: judge which of these candidate papers are genuinely relevant,",
        "and suggest new search keywords for papers that were relevant.",
        "",
    ]

    if research_context:
        prompt_parts.extend([
            "## Researcher's Background",
            research_context,
            "",
        ])

    prompt_parts.extend([
        "## Candidate Papers",
        "",
    ])

    for i, p in enumerate(candidates, 1):
        clusters = ", ".join(p.matched_clusters) if p.matched_clusters else "none"
        prompt_parts.extend([
            f"### [{i}] {p.title}",
            f"arXiv: {p.id} | Matched clusters: {clusters}",
            f"Authors: {', '.join(p.authors[:5])}{'...' if len(p.authors) > 5 else ''}",
            f"Abstract: {p.abstract[:500]}{'...' if len(p.abstract) > 500 else ''}",
            "",
        ])

    prompt_parts.extend([
        "## Your Task",
        "",
        "For each paper, respond with a JSON array:",
        "```json",
        "[",
        '  {"index": 1, "keep": true, "reason": "why relevant in 1 sentence"},',
        '  {"index": 2, "keep": false, "reason": "why not relevant"},',
        "  ...",
        "]",
        "```",
        "",
        "Then suggest new keywords that would have helped match relevant papers,",
        "or that describe topics you noticed are missing from the current clusters.",
        "```json",
        '{"new_keywords": [',
        '  {"keyword": "phonon polariton", "cluster": "Transport Methods", "reason": "related to coherent transport"},',
        "  ...",
        "]}",
        "```",
        "",
        "Be strict: only keep papers that a researcher in lattice dynamics, thermal transport,",
        "MLIPs, or anharmonic thermodynamics would genuinely want to read.",
        "Drop papers that are tangentially related (e.g., pure ML benchmarks without atomistic content).",
    ])

    return "\n".join(prompt_parts)


def parse_refinement_response(response: str) -> tuple[list[dict], list[dict]]:
    """Parse LLM refinement response into decisions and new keywords.
    
    Returns:
      (decisions, new_keywords) where
      decisions = [{"index": 1, "keep": True, "reason": "..."}, ...]
      new_keywords = [{"keyword": "...", "cluster": "...", "reason": "..."}, ...]
    """
    decisions = []
    new_keywords = []

    # Find JSON blocks
    json_blocks = re.findall(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", response)
    if not json_blocks:
        # Try to find inline JSON arrays
        json_blocks = re.findall(r"(\[[\s\S]*?\])", response)

    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if not isinstance(parsed, list):
                continue
            # Detect which type: decisions have "keep", keywords have "keyword"
            if parsed and "keep" in parsed[0]:
                decisions = parsed
            elif parsed and "keyword" in parsed[0]:
                new_keywords = parsed
        except json.JSONDecodeError:
            continue

    # Also try the {"new_keywords": [...]} format
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
    """Apply LLM refinement decisions and learn new keywords.
    
    Returns the filtered list of papers.
    """
    # Build index map
    keep_indices = set()
    for d in decisions:
        idx = d.get("index", 0) - 1  # 1-indexed to 0-indexed
        if d.get("keep", False) and 0 <= idx < len(candidates):
            keep_indices.add(idx)

    filtered = [candidates[i] for i in sorted(keep_indices)]

    # Learn new keywords
    if keyword_db and new_keywords:
        added = keyword_db.learn_keywords(new_keywords)
        if added:
            keyword_db.save()

    return filtered


# ── Convenience: full two-stage pipeline ──

def filter_papers(
    papers: list[Paper],
    config: FilterConfig,
    keyword_db: Optional[KeywordDB] = None,
) -> list[Paper]:
    """Stage 1 only (no LLM). For backward compatibility."""
    return keyword_filter(papers, config, keyword_db)
