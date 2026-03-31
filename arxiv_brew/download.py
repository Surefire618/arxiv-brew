"""
Paper content download and archiving.

Strategy: HTML first (structured, LLM-friendly), PDF fallback.

Archive layout:
  {paper_dir}/{YYYY-MM}/{arxiv_id}/
    ├── metadata.json
    └── content.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .arxiv_api import Paper, download_html, download_pdf_text

_DOWNLOAD_DELAY = 1.5  # seconds between downloads


def archive_paper(paper: Paper, base_dir: Path) -> Paper:
    """Download and archive a single paper. Returns updated Paper."""
    date_prefix = paper.published[:7] if paper.published else "unknown"
    paper_dir = base_dir / date_prefix / paper.id.replace("/", "_")
    paper_dir.mkdir(parents=True, exist_ok=True)

    # Save metadata
    (paper_dir / "metadata.json").write_text(
        json.dumps(paper.to_dict(), ensure_ascii=False, indent=2)
    )

    content_path = paper_dir / "content.md"

    # Skip if already downloaded
    if content_path.exists() and content_path.stat().st_size > 500:
        paper.content_path = str(content_path)
        paper.download_status = "cached"
        return paper

    # Try HTML first
    content = download_html(paper.id)
    source = "html"

    if content is None:
        content = download_pdf_text(paper.id, str(paper_dir / "paper.pdf"))
        source = "pdf"

    if content:
        header = f"# {paper.title}\n\n"
        header += f"**arXiv:** {paper.id}\n"
        header += f"**Authors:** {', '.join(paper.authors)}\n"
        header += f"**Published:** {paper.published}\n\n---\n\n"
        content_path.write_text(header + content)
        paper.content_path = str(content_path)
        paper.download_status = f"ok:{source}"
    else:
        paper.content_path = None
        paper.download_status = "failed"

    return paper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-download",
        description="Download full paper content for filtered papers.",
    )
    parser.add_argument("input", help="JSON from arxiv-pull (or - for stdin)")
    parser.add_argument("--paper-dir", default="papers", help="Archive directory")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args(argv)

    data = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
    papers = [Paper.from_dict(p) for p in data.get("papers", [])]
    base_dir = Path(args.paper_dir)

    print(f"[download] Processing {len(papers)} papers...", file=sys.stderr)

    for i, paper in enumerate(papers):
        status_before = paper.download_status
        archive_paper(paper, base_dir)
        label = "SKIP" if paper.download_status == "cached" else paper.download_status.upper()
        print(f"  [{label}] {paper.id}", file=sys.stderr)
        if i < len(papers) - 1 and paper.download_status != "cached":
            time.sleep(_DOWNLOAD_DELAY)

    ok = sum(1 for p in papers if p.download_status.startswith("ok"))
    cached = sum(1 for p in papers if p.download_status == "cached")
    failed = sum(1 for p in papers if p.download_status == "failed")
    print(f"[download] Done: {ok} new, {cached} cached, {failed} failed", file=sys.stderr)

    data["papers"] = [p.to_dict() for p in papers]
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
