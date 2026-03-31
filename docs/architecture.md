# Architecture

## Pipeline Flow

```
pipeline.main()
│
├─ KeywordDB.bootstrap()              Load or create config/keywords.json
│
├─ arxiv_api.fetch_new_ids_multi()    Scrape /list/{cat}/new → arXiv IDs
│     └─ fetch_new_ids() per category → HTTP GET + regex extract
│     └─ Deduplicate across categories → ~100-150 IDs
│
├─ arxiv_api.fetch_metadata()         Batch fetch via Atom API
│     └─ Chunks of 50 IDs → export.arxiv.org/api/query?id_list=...
│     └─ Parse XML → list[Paper] (title, authors, abstract, categories)
│
├─ filter.keyword_filter()            Stage 1: local keyword matching
│     └─ match_clusters() per paper
│           └─ Lowercase title + abstract
│           └─ Acronyms: word-boundary regex \bMACE\b
│           └─ Broad keywords: require context (phonon, DFT, lattice, ...)
│     └─ Records hits in KeywordDB
│     └─ ~3-10 papers pass
│
├─ download.archive_paper()           For each matched paper
│     └─ Create papers/{YYYY-MM}/{id}/
│     └─ Try download_html() → strip tags → content.md
│     └─ Fallback: download_pdf_text() → pdftotext/PyMuPDF
│
├─ summarize.build_summary()          For each paper
│     └─ extract_affiliations() → regex on first 4000 chars
│     └─ extract_corresponding_author() → email match or last author
│     └─ Summary fields left empty → digest uses full abstract
│
└─ summarize.format_digest()          Group by cluster → markdown
```

## Module Responsibilities

| Module | Purpose | External I/O |
|---|---|---|
| `config.py` | FilterConfig dataclass, defaults, merge logic | None |
| `arxiv_api.py` | Paper dataclass, HTTP scraping, API calls | arxiv.org |
| `keywords.py` | KeywordDB: bootstrap, hit tracking, learning | config/keywords.json |
| `filter.py` | Keyword matching + LLM refinement hooks | None |
| `pull.py` | CLI: orchestrates pull + filter | arxiv.org |
| `download.py` | CLI: fetches full text, manages archive | arxiv.org |
| `summarize.py` | CLI: extracts metadata, formats digest | None |
| `pipeline.py` | CLI: full pipeline in one command | arxiv.org |
| `db.py` | Database placeholder | None |

## Data Types

**Paper** (`arxiv_api.py`): Core dataclass flowing through the pipeline.
Fields: id, title, authors, abstract, published, categories, matched_clusters, affiliations, corresponding_author, content_path, download_status.

**FilterConfig** (`config.py`): Immutable config for the filter engine.
Fields: categories, topic_clusters (dict of keyword lists), word_boundary_keywords, broad_keywords, context_keywords.

**KeywordDB** (`keywords.py`): Persistent mutable keyword store.
Schema: clusters → keywords → {source, hits, added, reason}.
Sources: "default", "user" (from research profile), "llm" (from refinement feedback).
