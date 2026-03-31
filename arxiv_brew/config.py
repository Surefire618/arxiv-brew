"""
Configuration management.

Loads topic filters from:
  1. Explicit keyword file (YAML/JSON)
  2. User profile (skills, memory, research interests)
  3. Defaults
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_CATEGORIES = [
    "cond-mat.mtrl-sci",
    "cond-mat.stat-mech",
    "physics.comp-ph",
]

_DEFAULT_TOPIC_CLUSTERS: dict[str, list[str]] = {
    "ML for Atomistic Modeling": [
        "machine learning interatomic potential",
        "machine-learning interatomic potential",
        "MLIP", "MACE", "NequIP", "SO3krates",
        "equivariant neural network",
        "universal potential",
        "message passing neural network",
        "deep potential", "moment tensor potential",
        "active learning atomistic",
        "uncertainty quantification MD",
        "ML hamiltonian", "machine learning hamiltonian",
        "learned hamiltonian",
        "machine learning tight binding",
        "ML electronic structure",
        "deep learning force field",
        "neural network potential",
        "training set construction",
        "interatomic potential",
    ],
    "Transport Methods": [
        "lattice thermal conductivity",
        "thermal conductivity",
        "Green-Kubo", "Green Kubo",
        "Kubo-Greenwood", "Kubo Greenwood",
        "Boltzmann transport equation",
        "Wigner transport equation",
        "thermal transport",
        "phonon hydrodynamics",
        "heat flux operator",
        "Onsager coefficients",
        "electron-phonon coupled transport",
        "thermoelectric",
        "off-diagonal heat flux",
        "quasi-harmonic Green-Kubo", "QHGK",
        "phonon transport", "second sound", "phonon drag",
    ],
    "Anharmonic Thermodynamics": [
        "anharmonicity", "anharmonic",
        "phonon-phonon interaction",
        "self-consistent phonon", "SSCHA",
        "temperature dependent phonon",
        "temperature-dependent phonon",
        "free energy anharmonic",
        "phase transition lattice dynamics",
        "quasi-harmonic approximation",
        "renormalized phonon",
        "vibrational free energy",
        "thermodynamic integration",
        "thermodynamic stability",
        "Grüneisen", "Gruneisen",
        "phonon lifetime", "phonon linewidth",
        "phonon self-energy",
    ],
}

# Short acronyms that need word-boundary matching to avoid false positives
_WORD_BOUNDARY_KEYWORDS = {
    "MACE", "MLIP", "SSCHA", "QHGK", "NequIP", "SO3krates",
}

# Broad keywords that require atomistic/physics context to count
_BROAD_KEYWORDS = {
    "active learning", "uncertainty quantification",
    "thermal conductivity", "thermoelectric",
    "anharmonic", "anharmonicity",
}

_CONTEXT_KEYWORDS = [
    "phonon", "lattice", "crystal", "interatomic", "atomistic",
    "molecular dynamics", "DFT", "first-principles", "first principles",
    "ab initio", "density functional", "MLIP",
    "potential energy surface",
    "MACE", "NequIP", "VASP", "FHI-aims", "Quantum ESPRESSO",
    "solid", "alloy", "perovskite", "semiconductor", "insulator",
    "materials", "vibrational", "dispersion", "Brillouin",
]


@dataclass
class FilterConfig:
    """Paper filtering configuration."""
    categories: list[str] = field(default_factory=lambda: list(_DEFAULT_CATEGORIES))
    topic_clusters: dict[str, list[str]] = field(default_factory=lambda: dict(_DEFAULT_TOPIC_CLUSTERS))
    word_boundary_keywords: set[str] = field(default_factory=lambda: set(_WORD_BOUNDARY_KEYWORDS))
    broad_keywords: set[str] = field(default_factory=lambda: set(_BROAD_KEYWORDS))
    context_keywords: list[str] = field(default_factory=lambda: list(_CONTEXT_KEYWORDS))

    @classmethod
    def from_file(cls, path: str | Path) -> FilterConfig:
        """Load filter config from a JSON file."""
        data = json.loads(Path(path).read_text())
        return cls(
            categories=data.get("categories", _DEFAULT_CATEGORIES),
            topic_clusters=data.get("topic_clusters", _DEFAULT_TOPIC_CLUSTERS),
            word_boundary_keywords=set(data.get("word_boundary_keywords", _WORD_BOUNDARY_KEYWORDS)),
            broad_keywords=set(data.get("broad_keywords", _BROAD_KEYWORDS)),
            context_keywords=data.get("context_keywords", _CONTEXT_KEYWORDS),
        )

    @classmethod
    def from_profile(cls, profile_path: str | Path) -> FilterConfig:
        """Build filter config from a user research profile (MEMORY.md, USER.md, etc.).
        
        Reads markdown files and extracts research interests to augment
        default keywords. This enables adaptive filtering based on evolving
        research focus.
        """
        config = cls()
        profile = Path(profile_path)
        if not profile.exists():
            return config

        text = profile.read_text()

        # Extract keywords from structured sections
        # Look for lines like "- keyword" under research-relevant headers
        import re
        in_relevant_section = False
        extra_keywords: list[str] = []

        for line in text.splitlines():
            lower = line.lower().strip()
            if any(h in lower for h in [
                "research area", "research interest", "topic",
                "keyword", "focus", "direction",
            ]):
                in_relevant_section = True
                continue
            if line.startswith("#"):
                in_relevant_section = False
                continue
            if in_relevant_section and (line.strip().startswith("-") or line.strip().startswith("*")):
                kw = line.strip().lstrip("-*").strip()
                if 3 < len(kw) < 80:
                    extra_keywords.append(kw)

        # Add extracted keywords to a "User Interests" cluster
        if extra_keywords:
            config.topic_clusters["User Interests"] = extra_keywords

        return config

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
