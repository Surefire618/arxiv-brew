"""Local paper archive management: status, cleanup, deduplication."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import Settings

_P = "[brew]"


class SeenIndex:
    """Persistent set of previously processed paper IDs with timestamps."""

    def __init__(self, path: str | Path = "config/seen.json"):
        self.path = Path(path)
        self._data: dict[str, str] = {}  # id -> date first seen
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, ValueError):
                self._data = {}

    def __contains__(self, paper_id: str) -> bool:
        return paper_id in self._data

    def mark_seen(self, paper_ids: list[str]):
        today = datetime.now().strftime("%Y-%m-%d")
        for pid in paper_ids:
            if pid not in self._data:
                self._data[pid] = today

    def prune(self, retention_days: int = 90):
        """Remove entries older than retention_days to keep the index lean."""
        cutoff = time.time() - (retention_days * 86400)
        cutoff_date = datetime.fromtimestamp(cutoff).strftime("%Y-%m-%d")
        self._data = {k: v for k, v in self._data.items() if v >= cutoff_date}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def __len__(self) -> int:
        return len(self._data)


class PaperDB:

    def __init__(self, paper_dir: str = "papers", settings_path: str = "config/settings.json"):
        self.paper_dir = Path(paper_dir)
        self.settings = Settings.load(settings_path)

    def status(self) -> dict:
        if not self.paper_dir.exists():
            return {"paper_count": 0, "disk_bytes": 0, "oldest": None, "newest": None}

        papers = list(self.paper_dir.rglob("metadata.json"))
        total_bytes = sum(f.stat().st_size for f in self.paper_dir.rglob("*") if f.is_file())

        dates = []
        for p in papers:
            try:
                meta = json.loads(p.read_text())
                dates.append(meta.get("published", ""))
            except Exception:
                pass

        dates = sorted(d for d in dates if d)
        return {
            "paper_count": len(papers),
            "disk_mb": round(total_bytes / 1048576, 2),
            "oldest": dates[0] if dates else None,
            "newest": dates[-1] if dates else None,
            "retention_days": self.settings.paper_retention_days,
        }

    def cleanup(self, retention_days: int | None = None) -> dict:
        """Remove paper directories older than retention_days."""
        days = retention_days or self.settings.paper_retention_days
        if not self.paper_dir.exists():
            return {"removed": 0, "kept": 0}

        cutoff = time.time() - (days * 86400)
        removed = 0
        kept = 0

        for meta_file in self.paper_dir.rglob("metadata.json"):
            paper_dir = meta_file.parent
            if meta_file.stat().st_mtime < cutoff:
                import shutil
                shutil.rmtree(paper_dir)
                removed += 1
            else:
                kept += 1

        # Remove empty date directories
        for d in self.paper_dir.iterdir():
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

        return {"removed": removed, "kept": kept, "retention_days": days}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv-db", description="Paper archive management")
    parser.add_argument("command", choices=["status", "cleanup"])
    parser.add_argument("--paper-dir", default="papers")
    parser.add_argument("--retention-days", type=int, default=None,
                        help="Override retention days (default from config/settings.json)")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmation prompt (for cron jobs)")
    args = parser.parse_args(argv)

    db = PaperDB(paper_dir=args.paper_dir)

    if args.command == "status":
        print(json.dumps(db.status(), indent=2))
    elif args.command == "cleanup":
        status = db.status()
        days = args.retention_days or db.settings.paper_retention_days
        if not args.force and status["paper_count"] > 0:
            print(f"{_P} Will remove papers older than {days} days from {args.paper_dir}/", file=sys.stderr)
            print(f"{_P} Current archive: {status['paper_count']} papers, {status['disk_mb']} MB", file=sys.stderr)
            try:
                answer = input("Continue? [y/N] ")
                if answer.lower() not in ("y", "yes"):
                    print(f"{_P} Cancelled.", file=sys.stderr)
                    return 0
            except (EOFError, KeyboardInterrupt):
                print(f"\n{_P} Cancelled.", file=sys.stderr)
                return 0
        result = db.cleanup(retention_days=args.retention_days)
        print(f"{_P} Removed {result['removed']} papers, kept {result['kept']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
