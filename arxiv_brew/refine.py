"""Stage 2 refinement: apply LLM decisions to stage-1 candidates.

Provides both a Python API (refine_papers) and a CLI (arxiv-brew refine).
The agent only needs to supply the raw LLM response text; all parsing,
filtering, and keyword learning is handled internally.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .arxiv_api import Paper
from .filter import parse_refinement_response, apply_refinement
from .keywords import KeywordDB

_P = "[brew]"


def refine_papers(
    candidates_json: str | Path,
    llm_response: str,
    keyword_db_path: str | Path = "config/keywords.json",
) -> dict:
    """Single-function stage 2 refinement.

    Args:
        candidates_json: Path to stage-1 JSON output (from arxiv-brew --output).
        llm_response: Raw text response from the LLM.
        keyword_db_path: Path to keyword database.

    Returns:
        Dict with refined papers, learned keywords count, and digest.
    """
    data = json.loads(Path(candidates_json).read_text())
    candidates = [Paper.from_dict(p) for p in data.get("summaries", data.get("papers", []))]

    decisions, new_keywords = parse_refinement_response(llm_response)
    keyword_db = KeywordDB(keyword_db_path)
    refined = apply_refinement(candidates, decisions, new_keywords, keyword_db)

    return {
        "date": data.get("date", ""),
        "stage1_count": len(candidates),
        "stage2_count": len(refined),
        "kept_ids": [p.id for p in refined],
        "removed_ids": [p.id for p in candidates if p not in refined],
        "keywords_learned": len(new_keywords),
        "papers": [p.to_dict() for p in refined],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arxiv-brew refine",
        description="Apply LLM refinement to stage-1 candidates.",
    )
    parser.add_argument("candidates", help="Stage-1 JSON output file")
    parser.add_argument("llm_response", help="File containing raw LLM response text")
    parser.add_argument("--keyword-db", default="config/keywords.json",
                        help="Keyword database path")
    parser.add_argument("--output", "-o", default=None,
                        help="Write refined JSON to file (default: stdout)")
    args = parser.parse_args(argv)

    try:
        llm_text = Path(args.llm_response).read_text()
    except FileNotFoundError:
        print(f"{_P} LLM response file not found: {args.llm_response}", file=sys.stderr)
        return 2

    try:
        result = refine_papers(args.candidates, llm_text, args.keyword_db)
    except FileNotFoundError:
        print(f"{_P} Candidates file not found: {args.candidates}", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print(f"{_P} Invalid JSON in candidates file: {args.candidates}", file=sys.stderr)
        return 4

    print(f"{_P} Stage 2: {result['stage1_count']} → {result['stage2_count']} papers", file=sys.stderr)
    print(f"{_P} Learned {result['keywords_learned']} new keywords", file=sys.stderr)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"{_P} Saved to {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
