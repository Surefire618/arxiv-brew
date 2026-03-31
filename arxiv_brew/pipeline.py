"""
Full pipeline: pull → keyword filter → (optional LLM refine) → download → summarize.

Usage:
  arxiv-pipeline                                                    # defaults
  arxiv-pipeline --research-profile config/my_research.md           # with profile
  arxiv-pipeline --refine-prompt /tmp/refine.txt                    # stage 2 prep
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .arxiv_api import fetch_new_ids_multi, fetch_metadata
from .config import FilterConfig
from .filter import keyword_filter, build_refinement_prompt
from .keywords import KeywordDB
from .download import archive_paper
from .summarize import build_summary, format_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-pipeline",
        description="Full arXiv digest pipeline.",
    )
    parser.add_argument("--version", action="version", version="arxiv-brew 0.1.0")
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--keywords", metavar="FILE")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="User-created research profile (config/my_research.md)")
    parser.add_argument("--keyword-db", default="config/keywords.json")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--paper-dir", default="papers")
    parser.add_argument("--digest-dir", default="digests")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--digest-only", action="store_true")
    parser.add_argument("--refine-prompt", metavar="FILE",
                        help="Write LLM refinement prompt for stage 2")
    args = parser.parse_args(argv)

    date = datetime.now().strftime("%Y-%m-%d")

    # ── Keyword DB ──
    kw_db = KeywordDB(args.keyword_db)
    if args.bootstrap or not kw_db.data.get("clusters"):
        print(f"[pipeline] Bootstrapping keyword DB...", file=sys.stderr)
        kw_db.bootstrap(research_profile=args.research_profile, force=args.bootstrap)
        stats = kw_db.stats()
        print(f"[pipeline] Keywords: {stats['total_keywords']} ({stats['by_source']})", file=sys.stderr)

    config = kw_db.to_filter_config()
    if args.keywords:
        config = config.merge(FilterConfig.from_file(args.keywords))
    if args.categories:
        config.categories = args.categories

    # ── Pull ──
    print(f"[pipeline] {date} — scanning {len(config.categories)} categories", file=sys.stderr)
    all_ids = fetch_new_ids_multi(config.categories)
    print(f"[pipeline] {len(all_ids)} new papers", file=sys.stderr)

    if not all_ids:
        if args.digest_only:
            print("No relevant papers today.")
        return 0

    papers = fetch_metadata(all_ids)
    print(f"[pipeline] Metadata for {len(papers)}", file=sys.stderr)

    # ── Stage 1: Keyword filter ──
    filtered = keyword_filter(papers, config, kw_db)
    kw_db.save()
    print(f"[pipeline] Stage 1: {len(filtered)} matched", file=sys.stderr)
    for p in filtered:
        print(f"  ✓ [{', '.join(p.matched_clusters)}] {p.id}: {p.title[:65]}", file=sys.stderr)

    # ── Stage 2 prep ──
    if args.refine_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refine_prompt).write_text(prompt)
        print(f"[pipeline] Refinement prompt → {args.refine_prompt}", file=sys.stderr)

    if not filtered:
        if args.digest_only:
            print("No relevant papers today.")
        return 0

    # ── Download ──
    base_dir = Path(args.paper_dir)
    for i, paper in enumerate(filtered):
        archive_paper(paper, base_dir)
        print(f"  [{paper.download_status}] {paper.id}", file=sys.stderr)
        if i < len(filtered) - 1 and paper.download_status != "cached":
            time.sleep(1.5)

    # ── Summarize ──
    summaries = []
    for paper in filtered:
        content = None
        if paper.content_path and Path(paper.content_path).exists():
            content = Path(paper.content_path).read_text()
        summaries.append(build_summary(paper, content))

    digest_text = format_digest(date, summaries)
    digest_dir = Path(args.digest_dir)
    digest_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / f"{date}.md").write_text(digest_text)

    if args.digest_only:
        print(digest_text)
        return 0

    result = {
        "date": date,
        "total_scanned": len(papers),
        "total_matched": len(filtered),
        "keyword_db_stats": kw_db.stats(),
        "summaries": summaries,
        "digest_text": digest_text,
    }

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
