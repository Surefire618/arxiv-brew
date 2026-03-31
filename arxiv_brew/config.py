"""
Configuration management.

All topic-specific keywords come from the user's research profile
(config/my_research.md) or keyword database (config/keywords.json).

config.py only defines the data structures and loading logic — no
domain-specific defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default: scan broad physics categories. User overrides via CLI or config.
_DEFAULT_CATEGORIES = [
    "cond-mat",
    "physics",
]

# Word-boundary matching rules (structural, not domain-specific)
_WORD_BOUNDARY_DEFAULTS: set[str] = set()

# No built-in topic clusters — user defines these in my_research.md
_DEFAULT_TOPIC_CLUSTERS: dict[str, list[str]] = {}
_DEFAULT_BROAD_KEYWORDS: set[str] = set()
_DEFAULT_CONTEXT_KEYWORDS: list[str] = []


@dataclass
class FilterConfig:
    """Paper filtering configuration."""
    categories: list[str] = field(default_factory=lambda: list(_DEFAULT_CATEGORIES))
    topic_clusters: dict[str, list[str]] = field(default_factory=dict)
    word_boundary_keywords: set[str] = field(default_factory=lambda: set(_WORD_BOUNDARY_DEFAULTS))
    broad_keywords: set[str] = field(default_factory=lambda: set(_DEFAULT_BROAD_KEYWORDS))
    context_keywords: list[str] = field(default_factory=lambda: list(_DEFAULT_CONTEXT_KEYWORDS))

    @classmethod
    def from_file(cls, path: str | Path) -> FilterConfig:
        """Load filter config from a JSON file."""
        data = json.loads(Path(path).read_text())
        return cls(
            categories=data.get("categories", list(_DEFAULT_CATEGORIES)),
            topic_clusters=data.get("topic_clusters", {}),
            word_boundary_keywords=set(data.get("word_boundary_keywords", [])),
            broad_keywords=set(data.get("broad_keywords", [])),
            context_keywords=data.get("context_keywords", []),
        )

    def merge(self, other: FilterConfig) -> FilterConfig:
        """Merge another config into this one (additive)."""
        merged_clusters = dict(self.topic_clusters)
        for name, keywords in other.topic_clusters.items():
            existing = merged_clusters.get(name, [])
            merged_clusters[name] = list(dict.fromkeys(existing + keywords))

        return FilterConfig(
            categories=list(dict.fromkeys(self.categories + other.categories)),
            topic_clusters=merged_clusters,
            word_boundary_keywords=self.word_boundary_keywords | other.word_boundary_keywords,
            broad_keywords=self.broad_keywords | other.broad_keywords,
            context_keywords=list(dict.fromkeys(self.context_keywords + other.context_keywords)),
        )

    def is_empty(self) -> bool:
        """Check if this config has any keywords to filter with."""
        return not any(self.topic_clusters.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "categories": self.categories,
            "topic_clusters": self.topic_clusters,
            "word_boundary_keywords": sorted(self.word_boundary_keywords),
            "broad_keywords": sorted(self.broad_keywords),
            "context_keywords": self.context_keywords,
        }

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
