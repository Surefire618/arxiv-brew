"""
Dynamic keyword database with learning.

Manages a persistent keyword store that:
  1. Bootstraps from MEMORY.md / USER.md / hardcoded defaults
  2. Grows via LLM feedback (new terms discovered during refinement)
  3. Tracks keyword provenance and hit counts for pruning

Schema (keywords.json):
{
  "clusters": {
    "ML for Atomistic Modeling": {
      "keywords": {
        "MACE": {"source": "default", "hits": 12, "added": "2026-03-31"},
        "learned energy surface": {"source": "llm", "hits": 1, "added": "2026-04-02"},
        ...
      }
    }
  },
  "context_keywords": [...],
  "word_boundary_keywords": [...],
  "broad_keywords": [...],
  "last_updated": "2026-03-31"
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import FilterConfig, _DEFAULT_TOPIC_CLUSTERS


class KeywordDB:
    """Persistent, self-updating keyword database."""

    def __init__(self, path: str | Path = "config/keywords.json"):
        self.path = Path(path)
        self.data: dict = {"clusters": {}, "context_keywords": [], 
                           "word_boundary_keywords": [], "broad_keywords": [],
                           "last_updated": ""}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    # ── Bootstrap ──

    def bootstrap(
        self,
        research_profile: Optional[str | Path] = None,
        force: bool = False,
    ):
        """Initialize keyword DB from defaults + optional user research profile.
        
        Only runs if DB is empty or force=True.
        
        Args:
            research_profile: Optional path to a user-created research profile
                (e.g. config/my_research.md). This file is fully user-controlled
                and opt-in. We never read system files like MEMORY.md or USER.md.
            force: Re-bootstrap even if DB already exists.
        """
        if self.data.get("clusters") and not force:
            return

        # Start with hardcoded defaults
        config = FilterConfig()
        for cluster_name, keywords in config.topic_clusters.items():
            cluster = self.data.setdefault("clusters", {}).setdefault(cluster_name, {"keywords": {}})
            for kw in keywords:
                if kw not in cluster["keywords"]:
                    cluster["keywords"][kw] = {
                        "source": "default",
                        "hits": 0,
                        "added": datetime.now().strftime("%Y-%m-%d"),
                    }

        self.data["context_keywords"] = list(config.context_keywords)
        self.data["word_boundary_keywords"] = sorted(config.word_boundary_keywords)
        self.data["broad_keywords"] = sorted(config.broad_keywords)

        # Extract from user-provided research profile (opt-in only)
        if research_profile:
            path = Path(research_profile)
            if path.exists():
                extracted = self._extract_from_markdown(path)
                self._ingest_extracted(extracted, source="user")

        self.data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self.save()

    def _extract_from_markdown(self, path: Path) -> dict[str, list[str]]:
        """Extract research keywords from a markdown file.
        
        Looks for:
          - Bullet lists under relevant headers
          - Capitalized technical terms
          - Known patterns (acronyms, method names)
        """
        if not path.exists():
            return {}

        text = path.read_text()
        extracted: dict[str, list[str]] = {"general": []}

        # Strategy 1: Bullet items under research-relevant headers
        in_section = False
        current_section = "general"
        for line in text.splitlines():
            stripped = line.strip()
            lower = stripped.lower()

            # Detect section starts (headers or labeled lines like "- Research areas:")
            is_header = stripped.startswith("#")
            is_label = re.match(r"^[-*]\s+.*:$", stripped) and any(
                t in lower for t in ["research area", "research interest", "topic", "direction"]
            )
            if is_header or is_label:
                if is_header:
                    in_section = False
                for trigger in [
                    "research area", "research interest", "topic cluster",
                    "focus area", "direction", "reference repo",
                ]:
                    if trigger in lower:
                        in_section = True
                        if any(w in lower for w in ["machine learning", "mlip", "potential", "neural"]):
                            current_section = "ML for Atomistic Modeling"
                        elif any(w in lower for w in ["transport", "thermal", "conductivity"]):
                            current_section = "Transport Methods"
                        elif any(w in lower for w in ["anharmonic", "phonon", "thermodynamic"]):
                            current_section = "Anharmonic Thermodynamics"
                        else:
                            current_section = "general"
                        break
                if is_header:
                    continue

            if in_section and re.match(r"^\s*[-*]", line):
                kw = stripped.lstrip("-*").strip()
                # Clean up markdown formatting
                kw = re.sub(r"\*\*([^*]+)\*\*", r"\1", kw)
                kw = re.sub(r"\*([^*]+)\*", r"\1", kw)
                kw = kw.split("—")[0].split("–")[0].strip()  # cut at em/en dash
                # Skip sentences, code, and non-keyword content
                if len(kw) > 60 or len(kw) < 4:
                    continue
                if any(c in kw for c in ["(", ")", "`", "=", "{", "}", ":", "//"]):
                    continue
                if kw[0].islower() and " " not in kw:
                    continue  # skip single lowercase words
                extracted.setdefault(current_section, []).append(kw)

        # Strategy 2: Extract technical acronyms from full text
        acronyms = re.findall(r"\b([A-Z]{2,6})\b", text)
        known_relevant = {
            "QHGK", "MACE", "NequIP", "MLIP", "SSCHA", "BTE", "DFT",
            "VASP", "QHA", "GKM", "MTP", "GAP", "ACE", "SOAP",
        }
        for acr in set(acronyms):
            if acr in known_relevant:
                extracted.setdefault("general", []).append(acr)

        return extracted

    def _ingest_extracted(self, extracted: dict[str, list[str]], source: str):
        """Add extracted keywords to the database."""
        today = datetime.now().strftime("%Y-%m-%d")
        for section, keywords in extracted.items():
            # Map "general" to closest cluster or create new
            if section == "general":
                # Add to all clusters as low-priority
                for cluster_name in self.data.get("clusters", {}):
                    cluster = self.data["clusters"][cluster_name]
                    for kw in keywords:
                        if kw not in cluster["keywords"]:
                            cluster["keywords"][kw] = {
                                "source": source,
                                "hits": 0,
                                "added": today,
                            }
            else:
                cluster = self.data.setdefault("clusters", {}).setdefault(section, {"keywords": {}})
                for kw in keywords:
                    if kw not in cluster["keywords"]:
                        cluster["keywords"][kw] = {
                            "source": source,
                            "hits": 0,
                            "added": today,
                        }

    # ── Runtime access ──

    def to_filter_config(self) -> FilterConfig:
        """Convert current keyword DB into a FilterConfig for the filter engine."""
        topic_clusters = {}
        for cluster_name, cluster_data in self.data.get("clusters", {}).items():
            topic_clusters[cluster_name] = list(cluster_data.get("keywords", {}).keys())

        return FilterConfig(
            topic_clusters=topic_clusters,
            word_boundary_keywords=set(self.data.get("word_boundary_keywords", [])),
            broad_keywords=set(self.data.get("broad_keywords", [])),
            context_keywords=self.data.get("context_keywords", []),
        )

    def record_hit(self, cluster_name: str, keyword: str):
        """Increment hit count for a keyword."""
        cluster = self.data.get("clusters", {}).get(cluster_name, {})
        kw_data = cluster.get("keywords", {}).get(keyword)
        if kw_data:
            kw_data["hits"] = kw_data.get("hits", 0) + 1

    # ── LLM feedback ──

    def learn_keywords(self, new_keywords: list[dict]):
        """Ingest new keywords discovered by LLM during refinement.
        
        Each entry: {"keyword": "phonon polariton", "cluster": "Transport Methods", "reason": "..."}
        """
        today = datetime.now().strftime("%Y-%m-%d")
        added = 0
        for entry in new_keywords:
            kw = entry.get("keyword", "").strip()
            cluster_name = entry.get("cluster", "general")
            if not kw or len(kw) < 3:
                continue

            cluster = self.data.setdefault("clusters", {}).setdefault(cluster_name, {"keywords": {}})
            if kw not in cluster["keywords"]:
                cluster["keywords"][kw] = {
                    "source": "llm",
                    "hits": 0,
                    "added": today,
                    "reason": entry.get("reason", ""),
                }
                added += 1

        if added:
            self.data["last_updated"] = today
            self.save()

        return added

    # ── Persistence ──

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    # ── Stats ──

    def stats(self) -> dict:
        total = 0
        by_source = {}
        by_cluster = {}
        for cname, cdata in self.data.get("clusters", {}).items():
            kws = cdata.get("keywords", {})
            by_cluster[cname] = len(kws)
            total += len(kws)
            for kw, meta in kws.items():
                src = meta.get("source", "unknown")
                by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_keywords": total,
            "by_cluster": by_cluster,
            "by_source": by_source,
            "last_updated": self.data.get("last_updated", "never"),
        }
