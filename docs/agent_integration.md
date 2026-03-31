# Agent Integration

How to use arxiv-brew with an LLM agent (any LLM-based coding agent).

## Overview

The pipeline does all heavy lifting locally. The LLM only touches:
- ~5-15 candidate abstracts for refinement (stage 2)
- ~3-8 full papers for summary writing

## Workflow

```
1. Agent runs: python -m arxiv_brew --output result.json --refine-prompt refine.txt
2. Agent reads refine.txt → sends to LLM → gets response
3. Agent feeds response back via parse_refinement_response() + apply_refinement()
4. Agent reads each paper's content.md → writes research-notebook-style summaries
5. Agent delivers digest (email, chat, database, etc.)
```

## Stage 2: LLM Refinement

### Generate prompt

```bash
python -m arxiv_brew --output result.json --refine-prompt refine.txt
```

`refine.txt` contains a structured prompt with all stage-1 candidates.

### Parse LLM response

```python
from arxiv_brew.filter import parse_refinement_response, apply_refinement
from arxiv_brew.keywords import KeywordDB

decisions, new_keywords = parse_refinement_response(llm_response_text)
# decisions = [{"index": 1, "keep": True, "reason": "..."}, ...]
# new_keywords = [{"keyword": "phonon polariton", "cluster": "Transport Methods"}, ...]

keyword_db = KeywordDB("config/keywords.json")
final_papers = apply_refinement(candidates, decisions, new_keywords, keyword_db)
# new_keywords are persisted — next run matches them without LLM
```

## Keyword Learning

When the LLM suggests new keywords via `learn_keywords()`, they are:
- Added to `config/keywords.json` with `source: "llm"`
- Available for stage-1 matching on the next run
- Tracked with hit counts

Over time, the keyword database grows and LLM refinement becomes less necessary.

## Function Reference

| Function | What it does | Calls LLM? |
|---|---|---|
| `filter.build_refinement_prompt(papers)` | Formats candidates into an LLM prompt | No |
| `filter.parse_refinement_response(text)` | Extracts decisions + keywords from LLM output | No |
| `filter.apply_refinement(...)` | Applies decisions, persists new keywords | No |
| `keywords.KeywordDB.learn_keywords(kws)` | Writes new keywords to DB | No |

No function in this package calls an LLM.
