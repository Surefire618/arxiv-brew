"""Paper content download and archiving.

Strategy: HTML first (structured, LLM-friendly), PDF fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .arxiv_api import Paper, download_html, download_pdf_text

_P = "[brew]"
_DOWNLOAD_DELAY = 1.5
_MAX_WORKERS = 4


def archive_paper(paper: Paper, base_dir: Path) -> Paper:
    date_prefix = paper.published[:7] if paper.published else "unknown"
    paper_dir = base_dir / date_prefix / paper.id.replace("/", "_")
    paper_dir.mkdir(parents=True, exist_ok=True)

    (paper_dir / "metadata.json").write_text(
        json.dumps(paper.to_dict(), ensure_ascii=False, indent=2)
    )

    content_path = paper_dir / "content.md"

    if content_path.exists() and content_path.stat().st_size > 500:
        paper.content_path = str(content_path)
        paper.download_status = "cached"
        return paper

    content = download_html(paper)
    source = "html"

    if content is None:
        content = download_pdf_text(paper, str(paper_dir / "paper.pdf"))
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


def download_papers(papers: list[Paper], base_dir: Path,
                    max_workers: int = _MAX_WORKERS) -> list[Paper]:
    """Download papers concurrently with rate limiting."""
    rate_lock = threading.Lock()
    last_request = [0.0]  # mutable for closure

    def _rate_limited_archive(paper: Paper) -> Paper:
        with rate_lock:
            elapsed = time.monotonic() - last_request[0]
            if elapsed < _DOWNLOAD_DELAY:
                time.sleep(_DOWNLOAD_DELAY - elapsed)
            last_request[0] = time.monotonic()
        archive_paper(paper, base_dir)
        return paper

    # Separate cached (no download needed) from uncached
    cached = []
    to_download = []
    for paper in papers:
        date_prefix = paper.published[:7] if paper.published else "unknown"
        paper_dir = base_dir / date_prefix / paper.id.replace("/", "_")
        content_path = paper_dir / "content.md"
        if content_path.exists() and content_path.stat().st_size > 500:
            archive_paper(paper, base_dir)  # sets cached status
            cached.append(paper)
        else:
            to_download.append(paper)

    if to_download:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_rate_limited_archive, p): p for p in to_download}
            for future in as_completed(futures):
                paper = future.result()
                label = paper.download_status.upper()
                print(f"  [{label}] {paper.id}", file=sys.stderr)

    for paper in cached:
        print(f"  [CACHED] {paper.id}", file=sys.stderr)

    return papers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-download",
        description="Download full paper content for filtered papers.",
    )
    parser.add_argument("input", help="JSON from pull step (or - for stdin)")
    parser.add_argument("--paper-dir", default="papers")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--workers", type=int, default=_MAX_WORKERS,
                        help=f"Concurrent download threads (default: {_MAX_WORKERS})")
    args = parser.parse_args(argv)

    data = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
    papers = [Paper.from_dict(p) for p in data.get("papers", [])]
    base_dir = Path(args.paper_dir)

    print(f"{_P} Downloading {len(papers)} papers...", file=sys.stderr)
    download_papers(papers, base_dir, max_workers=args.workers)

    ok = sum(1 for p in papers if p.download_status.startswith("ok"))
    cached = sum(1 for p in papers if p.download_status == "cached")
    failed = sum(1 for p in papers if p.download_status == "failed")
    print(f"{_P} Done: {ok} new, {cached} cached, {failed} failed", file=sys.stderr)

    data["papers"] = [p.to_dict() for p in papers]
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
