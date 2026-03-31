"""Persistent keyword database with learning from LLM feedback."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import FilterConfig

_P = "[brew]"


class KeywordDB:

    def __init__(self, path: str | Path = "config/keywords.json"):
        self.path = Path(path)
        self.data: dict = {
            "clusters": {},
            "context_keywords": [],
            "word_boundary_keywords": [],
            "broad_keywords": [],
            "last_updated": "",
        }
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def init_from_profile(
        self,
        research_profile: str | Path,
        force: bool = False,
    ):
        """Build keyword DB from a research profile.

        Args:
            research_profile: Path to config/my_research.md.
            force: Rebuild even if DB already has data.
        """
        if self.data.get("clusters") and not force:
            return

        path = Path(research_profile)
        if not path.exists():
            return

        clusters, word_boundary, broad, context = self._parse_research_profile(path)

        for cluster_name, keywords in clusters.items():
            cluster = self.data.setdefault("clusters", {}).setdefault(
                cluster_name, {"keywords": {}}
            )
            for kw in keywords:
                if kw not in cluster["keywords"]:
                    cluster["keywords"][kw] = {
                        "source": "user",
                        "hits": 0,
                        "added": datetime.now().strftime("%Y-%m-%d"),
                    }

        if word_boundary:
            self.data["word_boundary_keywords"] = sorted(
                set(self.data.get("word_boundary_keywords", [])) | word_boundary
            )
        if broad:
            self.data["broad_keywords"] = sorted(
                set(self.data.get("broad_keywords", [])) | broad
            )
        if context:
            existing = self.data.get("context_keywords", [])
            self.data["context_keywords"] = list(dict.fromkeys(existing + context))

        self.data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self.save()

    def _parse_research_profile(
        self, path: Path
    ) -> tuple[dict[str, list[str]], set[str], set[str], list[str]]:
        """Parse research profile markdown into (clusters, word_boundary, broad, context)."""
        text = path.read_text()
        clusters: dict[str, list[str]] = {}
        categories: list[str] = []
        word_boundary: set[str] = set()
        broad: set[str] = set()
        context: list[str] = []

        current_section: str | None = None
        section_type = "cluster"

        for line in text.splitlines():
            stripped = line.strip()
            lower = stripped.lower()

            if stripped.startswith("#"):
                header = stripped.lstrip("#").strip().rstrip(":")
                header_lower = header.lower()

                if "word boundary" in header_lower or "word-boundary" in header_lower:
                    section_type = "word_boundary"
                    current_section = header
                elif "broad keyword" in header_lower:
                    section_type = "broad"
                    current_section = header
                elif "context keyword" in header_lower:
                    section_type = "context"
                    current_section = header
                elif "categor" in header_lower:
                    section_type = "categories"
                    current_section = header
                elif any(
                    skip in header_lower
                    for skip in ["install", "usage", "license", "how it works"]
                ):
                    current_section = None
                else:
                    section_type = "cluster"
                    current_section = header
                continue

            if current_section and re.match(r"^\s*[-*]", line):
                kw = stripped.lstrip("-*").strip()
                kw = re.sub(r"\*\*([^*]+)\*\*", r"\1", kw)
                kw = re.sub(r"\*([^*]+)\*", r"\1", kw)
                kw = kw.split("—")[0].split("–")[0].strip()

                if not kw or len(kw) > 80 or len(kw) < 2:
                    continue
                if kw.startswith("#") or kw.startswith("//"):
                    continue
                if any(c in kw for c in ["`", "=", "{", "}"]):
                    continue

                if section_type == "word_boundary":
                    word_boundary.add(kw)
                elif section_type == "broad":
                    broad.add(kw)
                elif section_type == "context":
                    context.append(kw)
                elif section_type == "categories":
                    categories.append(kw)
                else:
                    clusters.setdefault(current_section, []).append(kw)

        # Store categories in data for later retrieval
        if categories:
            self.data["categories"] = categories

        return clusters, word_boundary, broad, context

    def to_filter_config(self) -> FilterConfig:
        topic_clusters = {}
        for cluster_name, cluster_data in self.data.get("clusters", {}).items():
            topic_clusters[cluster_name] = list(
                cluster_data.get("keywords", {}).keys()
            )

        return FilterConfig(
            categories=self.data.get("categories", []),
            topic_clusters=topic_clusters,
            word_boundary_keywords=set(
                self.data.get("word_boundary_keywords", [])
            ),
            broad_keywords=set(self.data.get("broad_keywords", [])),
            context_keywords=self.data.get("context_keywords", []),
        )

    def record_hit(self, cluster_name: str, keyword: str):
        cluster = self.data.get("clusters", {}).get(cluster_name, {})
        kw_data = cluster.get("keywords", {}).get(keyword)
        if kw_data:
            kw_data["hits"] = kw_data.get("hits", 0) + 1

    def learn_keywords(self, new_keywords: list[dict]) -> int:
        """Ingest keywords discovered by LLM refinement.

        Each entry: {"keyword": "...", "cluster": "...", "reason": "..."}
        Returns number of new keywords added.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        added = 0
        for entry in new_keywords:
            kw = entry.get("keyword", "").strip()
            cluster_name = entry.get("cluster", "Uncategorized")
            if not kw or len(kw) < 2:
                continue

            cluster = self.data.setdefault("clusters", {}).setdefault(
                cluster_name, {"keywords": {}}
            )
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

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2)
        )

    def stats(self) -> dict:
        total = 0
        by_source: dict[str, int] = {}
        by_cluster: dict[str, int] = {}
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
