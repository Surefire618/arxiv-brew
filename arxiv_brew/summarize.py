"""
Paper summarization and digest generation.

This module:
  1. Extracts affiliations + corresponding author from full text
  2. Loads research context from user profile/memory for informed summaries
  3. Generates structured summary templates (for LLM completion)
  4. Formats the daily digest

The LLM summarization step is designed to be called from an agent context
(e.g. a cron job or coding assistant) that has access to an LLM.
For standalone use, outputs templates with abstract as fallback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .arxiv_api import Paper


# ── Affiliation & corresponding author extraction ──

def extract_affiliations(content: str) -> list[str]:
    """Extract institutional affiliations from paper full text."""
    header = content[:4000]
    affiliations: list[str] = []

    # LaTeX metadata pattern: organization=...
    for m in re.finditer(r"organization=([^,;}\n]+)", header, re.I):
        aff = m.group(1).strip().strip("{}")
        if aff and aff not in affiliations:
            affiliations.append(aff)

    # Institution names
    if not affiliations:
        inst_re = re.compile(
            r"(?:University|Institute|Department|Laboratory|School|College|"
            r"Université|Institut|Max Planck|Chinese Academy|"
            r"ETH|MIT|Caltech|Stanford|Princeton|Harvard|Oxford|Cambridge)"
            r"[^.\n]{5,80}",
            re.I
        )
        for m in inst_re.finditer(header):
            aff = m.group(0).strip()
            if len(aff) > 10 and aff not in affiliations:
                affiliations.append(aff)

    return affiliations[:5]


def extract_corresponding_author(content: str, authors: list[str]) -> Optional[str]:
    """Identify the corresponding author from full text."""
    header = content[:5000]

    # Explicit "corresponding author" mention
    m = re.search(
        r"correspond\w*\s+author[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
        header, re.I
    )
    if m:
        return m.group(1)

    # Match email addresses to author names
    emails = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", header)
    for email in emails:
        local = email.split("@")[0].lower().replace(".", "").replace("-", "")
        for author in authors:
            parts = author.lower().split()
            if any(part in local for part in parts if len(part) > 2):
                return author

    # Default heuristic: last author (common in physics)
    return authors[-1] if authors else None


# ── Research context loading ──

def load_research_context(profile_path: Optional[str] = None) -> str:
    """Load research context from a user-provided research profile.
    
    This is opt-in only. The profile is a user-created file
    (e.g. config/my_research.md) that the user explicitly provides.
    We never read system files like MEMORY.md or USER.md.
    
    Returns a context string for LLM summarization prompts.
    """
    if not profile_path:
        return ""
    path = Path(profile_path)
    if not path.exists():
        return ""

    text = path.read_text()
    if len(text) > 3000:
        text = text[:3000] + "\n[...truncated]"

    return f"# Research Context\n\n{text}\n\n---\n\n"


# ── Summary generation ──

def build_summary(paper: Paper, content: Optional[str] = None) -> dict:
    """Build a summary dict for a paper.
    
    Mechanically extracts what it can (affiliations, corresponding author).
    Fields marked [LLM] are templates for LLM completion.
    """
    affiliations = extract_affiliations(content) if content else []
    corresponding = extract_corresponding_author(content, paper.authors) if content else None
    if not corresponding and paper.authors:
        corresponding = paper.authors[-1]

    # Author string with corresponding marked
    author_str = ", ".join(paper.authors)
    if corresponding and corresponding in author_str:
        author_str = author_str.replace(corresponding, f"{corresponding}*")

    return {
        "id": paper.id,
        "title": paper.title,
        "authors_full": author_str,
        "corresponding_author": corresponding,
        "affiliations": affiliations,
        "affiliation_str": "; ".join(affiliations) if affiliations else "",
        "abs_url": paper.abs_url,
        "categories": paper.categories,
        "matched_clusters": paper.matched_clusters,
        "abstract": paper.abstract,
        "has_content": content is not None,
        "content_length": len(content) if content else 0,
        # LLM-generated fields (templates)
        "summary_background": "",
        "summary_contribution": "",
        "summary_significance": "",
    }


# ── Digest formatting ──

def format_digest_entry(s: dict) -> str:
    """Format a single paper for the digest."""
    lines = [
        f"**{s['title']}**",
        s["authors_full"],
    ]
    if s["affiliation_str"]:
        lines.append(s["affiliation_str"])
    lines.append(f"https://arxiv.org/abs/{s['id']}")
    lines.append("")

    # Use LLM summary if available, else full abstract
    if s.get("summary_background"):
        lines.extend([
            s["summary_background"],
            s["summary_contribution"],
            s["summary_significance"],
        ])
    else:
        lines.append(s["abstract"])

    lines.append("")
    return "\n".join(lines)


def format_digest(date: str, summaries: list[dict]) -> str:
    """Format the complete daily digest."""
    lines = [f"📰 **arXiv Digest — {date}**", ""]

    # Group by cluster
    cluster_order = [
        "ML for Atomistic Modeling",
        "Transport Methods",
        "Anharmonic Thermodynamics",
        "User Interests",
    ]
    cluster_papers: dict[str, list[dict]] = {}
    for s in summaries:
        for c in s.get("matched_clusters", ["Other"]):
            cluster_papers.setdefault(c, []).append(s)

    seen: set[str] = set()
    for cluster in cluster_order + [c for c in cluster_papers if c not in cluster_order]:
        papers = cluster_papers.get(cluster, [])
        if not papers:
            continue
        lines.extend([f"**{cluster}**", ""])
        for s in papers:
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            lines.append(format_digest_entry(s))

    if not seen:
        lines.append("No relevant papers today.")

    return "\n".join(lines)


# ── CLI ──

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-summarize",
        description="Generate paper summaries and daily digest.",
    )
    parser.add_argument("input", help="JSON from arxiv-download (or - for stdin)")
    parser.add_argument("--digest-dir", default="digests")
    parser.add_argument("--research-profile", metavar="FILE",
                        help="User-created research profile for context (opt-in)")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args(argv)

    data = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
    papers = [Paper.from_dict(p) for p in data.get("papers", [])]
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # Load research context (opt-in)
    context = load_research_context(args.research_profile) if args.research_profile else ""
    if context:
        print(f"[summarize] Loaded research context ({len(context)} chars)", file=sys.stderr)

    print(f"[summarize] Processing {len(papers)} papers...", file=sys.stderr)

    summaries = []
    for paper in papers:
        content = None
        if paper.content_path and Path(paper.content_path).exists():
            content = Path(paper.content_path).read_text()

        summary = build_summary(paper, content)
        summaries.append(summary)

        aff_status = "yes" if summary["affiliations"] else "no"
        print(f"  ✓ {paper.id}: aff={aff_status}, corr={summary['corresponding_author']}", file=sys.stderr)

        # Save per-paper summary
        if paper.content_path:
            summary_path = Path(paper.content_path).parent / "summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    # Generate digest
    digest_text = format_digest(date, summaries)
    digest_dir = Path(args.digest_dir)
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / f"{date}.md"
    digest_path.write_text(digest_text)
    print(f"[summarize] Digest: {digest_path}", file=sys.stderr)

    result = {
        "date": date,
        "research_context_loaded": bool(context),
        "summaries": summaries,
        "digest_path": str(digest_path),
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
