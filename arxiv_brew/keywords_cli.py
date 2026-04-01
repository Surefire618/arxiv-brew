"""CLI for keyword database management: list, add, remove, update, reset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import resolve_config_dir
from .keywords import KeywordDB
from . import exitcodes as EC

_P = "[brew]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-keywords",
        description="Manage the keyword database.",
    )
    parser.add_argument("--config-dir", default=None)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="Show all keywords by cluster")
    sub.add_parser("stats", help="Summary statistics")

    p_add = sub.add_parser("add", help="Add a keyword to a cluster")
    p_add.add_argument("cluster", help="Cluster name")
    p_add.add_argument("keyword", help="Keyword to add")

    p_rm = sub.add_parser("remove", help="Remove a keyword from a cluster")
    p_rm.add_argument("cluster", help="Cluster name")
    p_rm.add_argument("keyword", help="Keyword to remove")

    p_update = sub.add_parser("update", help="Sync keywords from research profile (preserves LLM keywords)")
    p_update.add_argument("--research-profile", default=None,
                          help="Path to research profile (default: config/my_research.md)")

    p_reset = sub.add_parser("reset", help="Rebuild keyword DB from profile (discards all existing data)")
    p_reset.add_argument("--research-profile", default=None,
                         help="Path to research profile (default: config/my_research.md)")

    args = parser.parse_args(argv)
    config_dir = resolve_config_dir(args.config_dir)
    db_path = config_dir / "keywords.json"
    db = KeywordDB(db_path)

    if not args.command:
        parser.print_help()
        return EC.SUCCESS

    if args.command == "list":
        return _cmd_list(db)

    if args.command == "stats":
        return _cmd_stats(db)

    if args.command == "add":
        if db.add_keyword(args.cluster, args.keyword):
            print(f"{_P} Added '{args.keyword}' to [{args.cluster}]", file=sys.stderr)
        else:
            print(f"{_P} '{args.keyword}' already exists in [{args.cluster}]", file=sys.stderr)
        return EC.SUCCESS

    if args.command == "remove":
        if db.remove_keyword(args.cluster, args.keyword):
            print(f"{_P} Removed '{args.keyword}' from [{args.cluster}]", file=sys.stderr)
        else:
            print(f"{_P} '{args.keyword}' not found in [{args.cluster}]", file=sys.stderr)
            return EC.CONFIG_ERROR
        return EC.SUCCESS

    if args.command == "update":
        profile = args.research_profile or str(config_dir / "my_research.md")
        if not Path(profile).exists():
            print(f"{_P} Profile not found: {profile}", file=sys.stderr)
            return EC.CONFIG_ERROR
        result = db.update_from_profile(profile)
        print(f"{_P} Updated: +{result['added']} added, -{result['removed']} removed", file=sys.stderr)
        _cmd_stats(db)
        return EC.SUCCESS

    if args.command == "reset":
        profile = args.research_profile or str(config_dir / "my_research.md")
        if not Path(profile).exists():
            print(f"{_P} Profile not found: {profile}", file=sys.stderr)
            return EC.CONFIG_ERROR
        result = db.reset_from_profile(profile)
        print(f"{_P} Reset: {result['added']} keywords from profile (LLM keywords discarded)", file=sys.stderr)
        _cmd_stats(db)
        return EC.SUCCESS

    return EC.SUCCESS


def _cmd_list(db: KeywordDB) -> int:
    keywords = db.list_keywords()
    if not keywords:
        print("No keywords. Run: arxiv-keywords update", file=sys.stderr)
        return EC.SUCCESS

    for cluster, items in keywords.items():
        print(f"\n{cluster} ({len(items)}):")
        for item in sorted(items, key=lambda x: -x["hits"]):
            src = item["source"]
            hits = item["hits"]
            tag = f"[{src}]" if src != "user" else ""
            hits_str = f" ({hits} hits)" if hits > 0 else ""
            print(f"  - {item['keyword']}{hits_str} {tag}".rstrip())

    return EC.SUCCESS


def _cmd_stats(db: KeywordDB) -> int:
    s = db.stats()
    print(f"Keywords: {s['total_keywords']}")
    print(f"Sources:  {s['by_source']}")
    print(f"Clusters: {s['by_cluster']}")
    print(f"Updated:  {s['last_updated']}")
    return EC.SUCCESS


if __name__ == "__main__":
    sys.exit(main())
