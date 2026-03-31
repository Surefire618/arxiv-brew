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


def main(argv: list[str] | None = None) -> int:
    global _quiet
    # Handle subcommands before argparse
    args_list = argv if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "init":
        from .init import run_init
        cfg = resolve_config_dir(None)
        return run_init(str(cfg))
    if args_list and args_list[0] == "refine":
        from .refine import main as refine_main
        return refine_main(args_list[1:])

    parser = argparse.ArgumentParser(
        prog="arxiv-brew",
        description="Full arXiv digest pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"arxiv-brew {__version__}")
    parser.add_argument("--config-dir", metavar="DIR", default=None,
                        help="Config directory (default: $ARXIV_BREW_CONFIG_DIR or ./config)")
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--keywords", metavar="FILE")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="Research profile (default: <config-dir>/my_research.md)")
    parser.add_argument("--keyword-db", default=None,
                        help="Keyword database (default: <config-dir>/keywords.json)")
    parser.add_argument("--init-keywords", action="store_true",
                        help="Rebuild keyword DB from profile (rule-based, no LLM)")
    parser.add_argument("--paper-dir", default="papers")
    parser.add_argument("--digest-dir", default="digests")
    parser.add_argument("--output", "-o", default=None,
                        help="Write full JSON to file (composable with --digest-only)")
    parser.add_argument("--digest-only", action="store_true",
                        help="Print digest to stdout instead of JSON")
    parser.add_argument("--no-dedup", "--force", action="store_true",
                        help="Reprocess all papers, ignoring seen index")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress all stderr logging")
    parser.add_argument("--refine-prompt", metavar="FILE",
                        help="Write LLM refinement prompt for stage 2")
    args = parser.parse_args(argv)

    _quiet = args.quiet
    date = datetime.now().strftime("%Y-%m-%d")
    cfg_dir = resolve_config_dir(args.config_dir)
    if not args.keyword_db:
        args.keyword_db = str(cfg_dir / "keywords.json")

    kw_db = KeywordDB(args.keyword_db)
    if args.init_keywords or not kw_db.data.get("clusters"):
        if not args.research_profile:
            _log(f"{_P} No keyword database found.")
            _log(f"{_P} Run: arxiv-brew init")
            return EC.CONFIG_ERROR
        _log(f"{_P} Initializing keywords from {args.research_profile}...")
        kw_db.init_from_profile(args.research_profile, force=args.init_keywords)
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

    _log(f"{_P} {date} — scanning {len(config.categories)} categories")
    try:
        all_ids = fetch_new_ids_multi(config.categories)
    except Exception as e:
        _log(f"{_P} Network error fetching paper IDs: {e}")
        return EC.NETWORK_ERROR
    _log(f"{_P} {len(all_ids)} new papers")

    if not args.no_dedup:
        before = len(all_ids)
        all_ids = [pid for pid in all_ids if pid not in seen]
        skipped = before - len(all_ids)
        if skipped:
            _log(f"{_P} {skipped} already seen, {len(all_ids)} remaining")

    if not all_ids:
        if args.digest_only:
            print("No relevant papers today.")
        return EC.NO_MATCHES

    try:
        papers = fetch_metadata(all_ids)
    except Exception as e:
        _log(f"{_P} Network error fetching metadata: {e}")
        return EC.NETWORK_ERROR
    _log(f"{_P} Metadata for {len(papers)}")

    filtered = keyword_filter(papers, config, kw_db)
    kw_db.save()

    # Mark all fetched IDs as seen (not just filtered) to avoid re-scanning
    seen.mark_seen([p.id for p in papers])
    seen.prune()
    seen.save()

    _log(f"{_P} {len(filtered)} matched")
    for p in filtered:
        _log(f"  ✓ [{', '.join(p.matched_clusters)}] ({p.relevance_score}) {p.id}: {p.title[:60]}")

    if args.refine_prompt and filtered:
        prompt = build_refinement_prompt(filtered)
        Path(args.refine_prompt).write_text(prompt)
        _log(f"{_P} Refinement prompt → {args.refine_prompt}")

    if not filtered:
        if args.digest_only:
            print("No relevant papers today.")
        return EC.NO_MATCHES

    base_dir = Path(args.paper_dir)
    download_papers(filtered, base_dir, quiet=_quiet)

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

    # --output always writes full JSON to file when specified
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))

    # stdout: --digest-only prints digest text, otherwise prints full JSON
    if args.digest_only:
        print(digest_text)
    elif not args.output:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return EC.SUCCESS


if __name__ == "__main__":
    sys.exit(main())
