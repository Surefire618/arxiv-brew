"""Full pipeline: pull → filter → download → summarize."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .arxiv_api import fetch_new_ids_multi, fetch_metadata
from .config import FilterConfig
from .filter import keyword_filter, build_refinement_prompt
from .keywords import KeywordDB
from .download import archive_paper
from .summarize import build_summary, format_digest

_P = "[brew]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-brew",
        description="Full arXiv digest pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"arxiv-brew {__version__}")
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--keywords", metavar="FILE")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="Research profile (config/my_research.md)")
    parser.add_argument("--keyword-db", default="config/keywords.json")
    parser.add_argument("--init-keywords", action="store_true",
                        help="Force re-initialize keyword DB from profile")
    parser.add_argument("--paper-dir", default="papers")
    parser.add_argument("--digest-dir", default="digests")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--digest-only", action="store_true")
    parser.add_argument("--refine-prompt", metavar="FILE",
                        help="Write LLM refinement prompt for stage 2")
    args = parser.parse_args(argv)

    date = datetime.now().strftime("%Y-%m-%d")

    kw_db = KeywordDB(args.keyword_db)
    if args.init_keywords or not kw_db.data.get("clusters"):
        if not args.research_profile:
            print(f"{_P} No keyword database found.", file=sys.stderr)
            print(f"{_P} Run: arxiv-brew init", file=sys.stderr)
            return 1
        print(f"{_P} Initializing keywords from {args.research_profile}...", file=sys.stderr)
        kw_db.init_from_profile(args.research_profile, force=args.init_keywords)
        stats = kw_db.stats()
        if stats["total_keywords"] == 0:
            print(f"{_P} No keywords extracted. Check your research profile.", file=sys.stderr)
            return 1
        print(f"{_P} Keywords: {stats['total_keywords']} ({stats['by_source']})", file=sys.stderr)

    config = kw_db.to_filter_config()
    if args.keywords:
        config = config.merge(FilterConfig.from_file(args.keywords))
    if args.categories:
        config.categories = args.categories
    if not config.categories:
        print(f"{_P} No categories configured. Add a ## Categories section to your research profile.", file=sys.stderr)
        return 1

    print(f"{_P} {date} — scanning {len(config.categories)} categories", file=sys.stderr)
    all_ids = fetch_new_ids_multi(config.categories)
    print(f"{_P} {len(all_ids)} new papers", file=sys.stderr)

    if not all_ids:
        if args.digest_only:
            print("No relevant papers today.")
        return 0

    papers = fetch_metadata(all_ids)
    print(f"{_P} Metadata for {len(papers)}", file=sys.stderr)

    filtered = keyword_filter(papers, config, kw_db)
    kw_db.save()
    print(f"{_P} {len(filtered)} matched", file=sys.stderr)
    for p in filtered:
        print(f"  ✓ [{', '.join(p.matched_clusters)}] {p.id}: {p.title[:65]}", file=sys.stderr)

    if args.refine_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refine_prompt).write_text(prompt)
        print(f"{_P} Refinement prompt → {args.refine_prompt}", file=sys.stderr)

    if not filtered:
        if args.digest_only:
            print("No relevant papers today.")
        return 0

    base_dir = Path(args.paper_dir)
    for i, paper in enumerate(filtered):
        archive_paper(paper, base_dir)
        print(f"  [{paper.download_status}] {paper.id}", file=sys.stderr)
        if i < len(filtered) - 1 and paper.download_status != "cached":
            time.sleep(1.5)

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
