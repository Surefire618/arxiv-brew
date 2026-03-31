# Agent Integration Guide

How LLM agents (Claude Code, Codex, OpenClaw, etc.) can use arxiv-brew.

## What this tool does

Filters today's new arXiv papers by keyword, downloads full text, and produces a structured digest. The agent's role: run the pipeline, optionally refine results with an LLM, and deliver the digest.

## Commands

All commands work via `python -m arxiv_brew` or the optional `arxiv-brew` bash wrapper.

### First-time setup

```bash
python -m arxiv_brew --research-profile config/my_research.md --init-keywords --digest-only
```

### Daily run

```bash
# Digest to stdout
python -m arxiv_brew --digest-only

# Full output with JSON
python -m arxiv_brew --output result.json --paper-dir papers --digest-dir digests
```

### With LLM refinement (stage 2)

```bash
# Step 1: pipeline generates a refinement prompt
python -m arxiv_brew --output result.json --refine-prompt refine.txt

# Step 2: agent sends refine.txt content to LLM, gets JSON response

# Step 3: agent calls Python API to apply decisions
```

### Archive cleanup

```bash
python -m arxiv_brew.db cleanup --retention-days 14
python -m arxiv_brew.db status
```

## Python API for stage 2

```python
from arxiv_brew.filter import parse_refinement_response, apply_refinement
from arxiv_brew.keywords import KeywordDB

# Parse LLM's JSON response
decisions, new_keywords = parse_refinement_response(llm_response_text)

# Apply: filters papers + persists new keywords for future runs
keyword_db = KeywordDB("config/keywords.json")
final_papers = apply_refinement(candidates, decisions, new_keywords, keyword_db)
```

### What `parse_refinement_response` expects

The LLM response should contain two JSON blocks:

```json
[{"index": 1, "keep": true, "reason": "relevant"}, ...]
```

```json
{"new_keywords": [{"keyword": "phonon polariton", "cluster": "Transport", "reason": "..."}]}
```

### What `learn_keywords` does

New keywords are written to `config/keywords.json` with `source: "llm"`. On the next run, they participate in stage 1 keyword matching — reducing the need for LLM refinement over time.

## Output formats

### `--output result.json`

```json
{
  "date": "2026-04-01",
  "total_scanned": 142,
  "total_matched": 5,
  "keyword_db_stats": {"total_keywords": 80, "by_source": {"user": 65, "llm": 15}},
  "summaries": [
    {
      "id": "2604.00123",
      "title": "...",
      "authors_full": "A, B, C*",
      "corresponding_author": "C",
      "affiliations": ["University of ..."],
      "matched_clusters": ["ML Potentials"],
      "abstract": "..."
    }
  ],
  "digest_text": "📰 **arXiv Digest — 2026-04-01**\n..."
}
```

### `--digest-only`

Prints the markdown digest to stdout (no JSON wrapper).

### `--refine-prompt FILE`

Writes a prompt with all stage-1 candidates for LLM evaluation.
