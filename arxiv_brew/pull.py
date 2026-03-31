"""Discover and filter today's new arXiv papers."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .arxiv_api import fetch_new_ids_multi, fetch_metadata
from .config import FilterConfig
from .db import SeenIndex
from . import exitcodes as EC
from .filter import keyword_filter, build_refinement_prompt
from .keywords import KeywordDB

_P = "[brew]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-pull",
        description="Pull and filter today's new arXiv papers.",
    )
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--keywords", metavar="FILE", help="Keyword config JSON")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="Research profile (e.g. config/my_research.md)")
    parser.add_argument("--keyword-db", metavar="FILE", default="config/keywords.json")
    parser.add_argument("--init-keywords", action="store_true",
                        help="Rebuild keyword DB from profile (rule-based, no LLM)")
    parser.add_argument("--output", "-o", metavar="FILE")
    parser.add_argument("--all", action="store_true", help="Output all papers")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Skip cross-day deduplication")
    parser.add_argument("--refinement-prompt", metavar="FILE",
                        help="Write LLM refinement prompt to file")
    args = parser.parse_args(argv)

    kw_db = KeywordDB(args.keyword_db)

    if args.init_keywords or not kw_db.data.get("clusters"):
        if not args.research_profile:
            print(f"{_P} No keyword database found.", file=sys.stderr)
            print(f"{_P} Run: arxiv-brew init", file=sys.stderr)
            return EC.CONFIG_ERROR
        print(f"{_P} Initializing keywords from {args.research_profile}...", file=sys.stderr)
        kw_db.init_from_profile(args.research_profile, force=args.init_keywords)
        stats = kw_db.stats()
        if stats["total_keywords"] == 0:
            print(f"{_P} No keywords extracted. Check your research profile format.", file=sys.stderr)
            return EC.CONFIG_ERROR
        print(f"{_P} Keywords: {stats['total_keywords']} ({stats['by_source']})", file=sys.stderr)

    config = kw_db.to_filter_config()

    if args.keywords:
        config = config.merge(FilterConfig.from_file(args.keywords))
    if args.categories:
        config.categories = args.categories
    if not config.categories:
        print(f"{_P} No categories configured. Add a ## Categories section to your research profile.", file=sys.stderr)
        return EC.CONFIG_ERROR

    seen = SeenIndex()

    print(f"{_P} Scanning {len(config.categories)} categories...", file=sys.stderr)
    try:
        all_ids = fetch_new_ids_multi(config.categories)
    except Exception as e:
        print(f"{_P} Network error fetching paper IDs: {e}", file=sys.stderr)
        return EC.NETWORK_ERROR
    print(f"{_P} {len(all_ids)} unique new papers", file=sys.stderr)

    if not args.no_dedup:
        before = len(all_ids)
        all_ids = [pid for pid in all_ids if pid not in seen]
        skipped = before - len(all_ids)
        if skipped:
            print(f"{_P} {skipped} already seen, {len(all_ids)} remaining", file=sys.stderr)

    if not all_ids:
        result = {"date": datetime.now().strftime("%Y-%m-%d"), "papers": []}
        _output(result, args.output)
        return EC.NO_MATCHES

    try:
        papers = fetch_metadata(all_ids)
    except Exception as e:
        print(f"{_P} Network error fetching metadata: {e}", file=sys.stderr)
        return EC.NETWORK_ERROR
    print(f"{_P} Metadata for {len(papers)} papers", file=sys.stderr)

    if args.all:
        for p in papers:
            p.matched_clusters = []
        filtered = papers
    else:
        filtered = keyword_filter(papers, config, kw_db)
        kw_db.save()

    seen.mark_seen([p.id for p in papers])
    seen.prune()
    seen.save()

    print(f"{_P} {len(filtered)} papers matched", file=sys.stderr)
    for p in filtered:
        clusters = ", ".join(p.matched_clusters)
        print(f"  ✓ [{clusters}] ({p.relevance_score}) {p.id}: {p.title[:60]}", file=sys.stderr)

    if args.refinement_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refinement_prompt).write_text(prompt)
        print(f"{_P} Refinement prompt → {args.refinement_prompt}", file=sys.stderr)

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_scanned": len(papers),
        "total_matched": len(filtered),
        "categories_scanned": config.categories,
        "keyword_db_stats": kw_db.stats(),
        "papers": [p.to_dict() for p in filtered],
    }
    _output(result, args.output)
    return EC.SUCCESS


def _output(data: dict, path: str | None):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        print(f"{_P} Saved to {path}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
