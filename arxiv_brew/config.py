"""Configuration dataclasses and loading logic."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def resolve_config_dir(cli_arg: str | None = None) -> Path:
    """Resolve the config directory.

    Priority: --config-dir flag > $ARXIV_BREW_CONFIG_DIR > ./config
    """
    if cli_arg:
        return Path(cli_arg)
    env = os.environ.get("ARXIV_BREW_CONFIG_DIR")
    if env:
        return Path(env)
    return Path("config")


@dataclass
class FilterConfig:
    categories: list[str] = field(default_factory=list)
    topic_clusters: dict[str, list[str]] = field(default_factory=dict)
    word_boundary_keywords: set[str] = field(default_factory=set)
    broad_keywords: set[str] = field(default_factory=set)
    context_keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> FilterConfig:
        data = json.loads(Path(path).read_text())
        return cls(
            categories=data.get("categories", []),
            topic_clusters=data.get("topic_clusters", {}),
            word_boundary_keywords=set(data.get("word_boundary_keywords", [])),
            broad_keywords=set(data.get("broad_keywords", [])),
            context_keywords=data.get("context_keywords", []),
        )

    def merge(self, other: FilterConfig) -> FilterConfig:
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


@dataclass
class Settings:
    paper_retention_days: int = 30

    @classmethod
    def load(cls, path: str | Path = "config/settings.json") -> Settings:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text())
            return cls(paper_retention_days=data.get("paper_retention_days", 30))
        return cls()

    def save(self, path: str | Path = "config/settings.json"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({
            "paper_retention_days": self.paper_retention_days,
        }, indent=2))
