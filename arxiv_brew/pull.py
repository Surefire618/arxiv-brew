"""
arxiv_new_pull — Discover and filter today's new arXiv papers.

Two-stage filtering:
  Stage 1: Keyword matching (fast, local, always runs)
  Stage 2: LLM refinement (optional, when --refine-prompt is set)

Keyword sources (merged in order):
  1. Built-in defaults
  2. --keywords FILE (explicit keyword config)
  3. --research-profile FILE (opt-in user research profile)
  4. Keyword DB (config/keywords.json — grows over time via LLM feedback)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .arxiv_api import fetch_new_ids_multi, fetch_metadata
from .config import FilterConfig
from .filter import keyword_filter, build_refinement_prompt
from .keywords import KeywordDB


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-pull",
        description="Pull and filter today's new arXiv papers.",
    )
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--keywords", metavar="FILE", help="Keyword config JSON")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="User-created research profile (e.g. config/my_research.md)")
    parser.add_argument("--keyword-db", metavar="FILE", default="config/keywords.json",
                        help="Keyword database path (default: config/keywords.json)")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Force re-bootstrap keyword DB")
    parser.add_argument("--output", "-o", metavar="FILE")
    parser.add_argument("--all", action="store_true", help="Output all papers")
    parser.add_argument("--refinement-prompt", metavar="FILE",
                        help="Write LLM refinement prompt to file (for stage 2)")
    args = parser.parse_args(argv)

    # ── Build keyword DB ──
    kw_db = KeywordDB(args.keyword_db)

    if args.bootstrap or not kw_db.data.get("clusters"):
        print("[pull] Bootstrapping keyword database...", file=sys.stderr)
        kw_db.bootstrap(
            research_profile=args.research_profile,
            force=args.bootstrap,
        )
        stats = kw_db.stats()
        print(f"[pull] Keywords: {stats['total_keywords']} total, "
              f"by source: {stats['by_source']}", file=sys.stderr)

    config = kw_db.to_filter_config()

    if args.keywords:
        config = config.merge(FilterConfig.from_file(args.keywords))
    if args.categories:
        config.categories = args.categories

    # ── Pull ──
    print(f"[pull] Scanning {len(config.categories)} categories...", file=sys.stderr)
    all_ids = fetch_new_ids_multi(config.categories)
    print(f"[pull] {len(all_ids)} unique new papers", file=sys.stderr)

    if not all_ids:
        result = {"date": datetime.now().strftime("%Y-%m-%d"), "papers": []}
        _output(result, args.output)
        return 0

    papers = fetch_metadata(all_ids)
    print(f"[pull] Metadata for {len(papers)} papers", file=sys.stderr)

    # ── Stage 1: Keyword filter ──
    if args.all:
        for p in papers:
            p.matched_clusters = []
        filtered = papers
    else:
        filtered = keyword_filter(papers, config, kw_db)
        kw_db.save()

    print(f"[pull] Stage 1: {len(filtered)} papers matched", file=sys.stderr)
    for p in filtered:
        clusters = ", ".join(p.matched_clusters)
        print(f"  ✓ [{clusters}] {p.id}: {p.title[:70]}", file=sys.stderr)

    # ── Stage 2 prep ──
    if args.refinement_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refinement_prompt).write_text(prompt)
        print(f"[pull] Refinement prompt → {args.refinement_prompt}", file=sys.stderr)

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_scanned": len(papers),
        "total_matched": len(filtered),
        "categories_scanned": config.categories,
        "keyword_db_stats": kw_db.stats(),
        "papers": [p.to_dict() for p in filtered],
    }
    _output(result, args.output)
    return 0


def _output(data: dict, path: str | None):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        print(f"[pull] Saved to {path}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
