"""Entry point: arxiv-brew CLI with subcommands."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .arxiv_api import fetch_new_ids_multi, fetch_metadata
from .config import FilterConfig, resolve_config_dir
from .db import SeenIndex
from . import exitcodes as EC
from .filter import keyword_filter, build_refinement_prompt
from .keywords import KeywordDB
from .download import archive_paper, download_papers
from .summarize import build_summary, format_digest

_P = "[brew]"
_quiet = False


def _log(*args, **kwargs):
    if not _quiet:
        print(*args, file=sys.stderr, **kwargs)


def _brew(args) -> int:
    """Run the full pipeline: pull → filter → download → digest."""
    global _quiet
    _quiet = args.quiet
    date = datetime.now().strftime("%Y-%m-%d")
    cfg_dir = resolve_config_dir(args.config_dir)
    keyword_db_path = args.keyword_db or str(cfg_dir / "keywords.json")

    kw_db = KeywordDB(keyword_db_path)
    if args.update_keywords or not kw_db.data.get("clusters"):
        if not args.research_profile:
            _log(f"{_P} No keyword database found.")
            _log(f"{_P} Run: arxiv-brew init")
            return EC.CONFIG_ERROR
        _log(f"{_P} Updating keywords from {args.research_profile}...")
        result = kw_db.update_from_profile(args.research_profile)
        _log(f"{_P} Keywords: +{result['added']} added, -{result['removed']} removed")
        stats = kw_db.stats()
        if stats["total_keywords"] == 0:
            _log(f"{_P} No keywords extracted. Check your research profile.")
            return EC.CONFIG_ERROR
        _log(f"{_P} Keywords: {stats['total_keywords']} ({stats['by_source']})")

    config = kw_db.to_filter_config()
    if args.keywords:
        config = config.merge(FilterConfig.from_file(args.keywords))
    if args.categories:
        config.categories = args.categories
    if not config.categories:
        _log(f"{_P} No categories configured. Add a ## Categories section to your research profile.")
        return EC.CONFIG_ERROR

    seen = SeenIndex(cfg_dir / "seen.json")

    # Pull + metadata: always run (cheap)
    _log(f"{_P} {date} — scanning {len(config.categories)} categories")
    try:
        all_ids = fetch_new_ids_multi(config.categories)
    except Exception as e:
        _log(f"{_P} Network error fetching paper IDs: {e}")
        return EC.NETWORK_ERROR
    _log(f"{_P} {len(all_ids)} new papers")

    if not all_ids:
        if not args.json:
            print("No relevant papers today.")
        return EC.NO_MATCHES

    try:
        papers = fetch_metadata(all_ids)
    except Exception as e:
        _log(f"{_P} Network error fetching metadata: {e}")
        return EC.NETWORK_ERROR
    _log(f"{_P} Metadata for {len(papers)}")

    # Keyword filter: always run (cheap, <1s)
    filtered = keyword_filter(papers, config, kw_db)
    kw_db.save()

    _log(f"{_P} {len(filtered)} matched")
    for p in filtered:
        _log(f"  ✓ [{', '.join(p.matched_clusters)}] ({p.relevance_score}) {p.id}: {p.title[:60]}")

    if args.refine_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refine_prompt).write_text(prompt)
        _log(f"{_P} Refinement prompt → {args.refine_prompt}")

    if not filtered:
        if not args.json:
            print("No relevant papers today.")
        return EC.NO_MATCHES

    # Download: skip papers already seen (expensive)
    if not args.no_dedup:
        before = len(filtered)
        filtered = [p for p in filtered if p.id not in seen]
        skipped = before - len(filtered)
        if skipped:
            _log(f"{_P} {skipped} already downloaded, {len(filtered)} new")

    if not filtered:
        if not args.json:
            print("No new papers to download (all previously processed).")
        return EC.NO_MATCHES

    base_dir = Path(args.paper_dir)
    download_papers(filtered, base_dir, quiet=_quiet)

    # Mark only downloaded papers as seen
    seen.mark_seen([p.id for p in filtered])
    seen.prune()
    seen.save()

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

    result = {
        "date": date,
        "total_scanned": len(papers),
        "total_matched": len(filtered),
        "keyword_db_stats": kw_db.stats(),
        "summaries": summaries,
        "digest_text": digest_text,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(digest_text)

    return EC.SUCCESS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-brew",
        description="Keyword-based arXiv paper filtering and digest generation.",
    )
    parser.add_argument("--version", action="version", version=f"arxiv-brew {__version__}")
    sub = parser.add_subparsers(dest="command")

    # brew
    p_brew = sub.add_parser("brew", help="Run the pipeline and print today's digest")
    p_brew.add_argument("--config-dir", metavar="DIR", default=None)
    p_brew.add_argument("--categories", nargs="+", default=None)
    p_brew.add_argument("--keywords", metavar="FILE")
    p_brew.add_argument("--research-profile", metavar="FILE")
    p_brew.add_argument("--keyword-db", default=None)
    p_brew.add_argument("--update-keywords", action="store_true",
                        help="Sync keyword DB from research profile before running")
    p_brew.add_argument("--paper-dir", default="papers")
    p_brew.add_argument("--digest-dir", default="digests")
    p_brew.add_argument("--output", "-o", default=None,
                        help="Also write full JSON to file")
    p_brew.add_argument("--json", action="store_true",
                        help="Output JSON instead of readable digest")
    p_brew.add_argument("--no-dedup", "--force", action="store_true",
                        help="Reprocess all papers, ignoring seen index")
    p_brew.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress stderr logging")
    p_brew.add_argument("--refine-prompt", metavar="FILE",
                        help="Write LLM refinement prompt for stage 2")

    # init
    sub.add_parser("init", help="Set up config/my_research.md and config/settings.json")

    # refine
    p_refine = sub.add_parser("refine", help="Apply LLM refinement to stage-1 candidates")
    p_refine.add_argument("candidates", help="Stage-1 JSON output file")
    p_refine.add_argument("llm_response", help="File containing raw LLM response text")
    p_refine.add_argument("--keyword-db", default="config/keywords.json")
    p_refine.add_argument("--output", "-o", default=None)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EC.SUCCESS

    if args.command == "brew":
        return _brew(args)

    if args.command == "init":
        from .init import run_init
        cfg = resolve_config_dir(None)
        return run_init(str(cfg))

    if args.command == "refine":
        from .refine import main as refine_main
        return refine_main([args.candidates, args.llm_response,
                           "--keyword-db", args.keyword_db]
                          + (["--output", args.output] if args.output else []))

    return EC.SUCCESS


if __name__ == "__main__":
    sys.exit(main())
