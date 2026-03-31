# arxiv-brew

Keyword-based arXiv paper filtering and digest generation. Designed to be called by LLM agents for automated daily literature monitoring.

Pulls today's new submissions from configurable arXiv categories, filters against a persistent keyword database, downloads full text, and outputs a structured digest. The pipeline runs standalone, but is built to integrate with agent workflows that add LLM-powered refinement and summarization.

## Install

```bash
git clone https://github.com/Surefire618/arxiv-brew.git
cd arxiv-brew
```

Python 3.10+, stdlib only. No external dependencies.

## Usage

### Run the pipeline

```bash
# Print today's digest to stdout
./arxiv-brew run --digest-only

# Full pipeline with file output
./arxiv-brew run --output result.json --paper-dir papers --digest-dir digests
```

### Personalize

```bash
cp config/my_research.md.template config/my_research.md
# Edit with your research interests, then:
./arxiv-brew run --research-profile config/my_research.md --bootstrap --digest-only
```

### Step by step

```bash
./arxiv-brew pull -o papers.json
./arxiv-brew download papers.json -o downloaded.json
./arxiv-brew summarize downloaded.json --digest-dir digests/
```

### Agent integration

The pipeline produces structured JSON output and optional LLM refinement prompts. An agent can:

1. Run the pipeline and get filtered candidates
2. Use the refinement prompt to judge relevance and suggest new keywords
3. Feed keywords back — they are persisted for future runs, reducing LLM dependency over time

```bash
./arxiv-brew run --output result.json --refine-prompt refine.txt
```

See [docs/agent_integration.md](docs/agent_integration.md) for the full workflow.

## How it works

1. **Pull** — scrapes `arxiv.org/list/{category}/new`, fetches metadata via Atom API
2. **Filter** — two-stage: keyword matching (always), LLM refinement (optional)
3. **Download** — full text via HTML (preferred) or PDF fallback
4. **Summarize** — extracts affiliations, formats digest grouped by topic cluster

The keyword database grows over time via LLM feedback — new terms discovered during refinement are persisted for future matching.

## Configuration

Default categories: `cond-mat.mtrl-sci`, `cond-mat.stat-mech`, `physics.comp-ph`

Default topic clusters: ML for Atomistic Modeling, Transport Methods, Anharmonic Thermodynamics

Override with `--categories`, `--keywords FILE`, or `--research-profile FILE`.

## License

MIT
