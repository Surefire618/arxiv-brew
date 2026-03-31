"""Interactive setup: create config/my_research.md and config/settings.json."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .config import Settings

_P = "[brew]"


def run_init(config_dir: str = "config") -> int:
    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)

    profile = config_path / "my_research.md"
    template = config_path / "my_research.md.template"

    if profile.exists():
        print(f"{_P} {profile} already exists. Edit it directly or delete to re-init.", file=sys.stderr)
    else:
        if template.exists():
            shutil.copy(template, profile)
        else:
            # Fallback: write template directly
            profile.write_text(_DEFAULT_TEMPLATE)
        print(f"{_P} Created {profile}", file=sys.stderr)
        print(f"{_P} Edit it with your research topics and keywords.", file=sys.stderr)

    settings_path = config_path / "settings.json"
    if not settings_path.exists():
        Settings().save(str(settings_path))
        print(f"{_P} Created {settings_path} (paper_retention_days=30)", file=sys.stderr)

    print(f"\n{_P} Next steps:", file=sys.stderr)
    print(f"  1. Edit {profile}", file=sys.stderr)
    print(f"  2. Run: arxiv-brew --research-profile {profile} --init-keywords --digest-only", file=sys.stderr)

    return 0


_DEFAULT_TEMPLATE = """\
# My Research Profile
#
# This file defines your arxiv-brew keywords and categories.
# --init-keywords parses this file with pure rules (no LLM) to build
# config/keywords.json. Re-run with --init-keywords after editing.
#
# Usage:
#   arxiv-brew --research-profile config/my_research.md --init-keywords --digest-only
#
# ## File format
#
# - `## Categories:` — arXiv categories to scan (required)
# - `## <Topic Name>:` — keyword cluster; each `- item` is a keyword
# - `## Word boundary keywords:` — short acronyms matched as whole words only
# - `## Broad keywords:` — generic terms that require a context keyword
# - `## Context keywords:` — co-occurring terms that validate broad keywords
#
# Lines starting with # inside a section are ignored.
# Keywords longer than 80 chars or containing backticks/braces are skipped.

## Categories:
# arXiv categories to scan daily.
# Full list: https://arxiv.org/category_taxonomy
  - cond-mat.mtrl-sci
  - physics.comp-ph
  - cs.LG

## Thermal Transport:
  - thermal conductivity
  - lattice thermal conductivity
  - phonon transport
  - Green-Kubo
  - Boltzmann transport equation
  - anharmonic phonon
  - phonon scattering

## ML Potentials:
  - machine learning potential
  - neural network potential
  - MACE
  - MLIP
  - active learning
  - molecular dynamics

## Word boundary keywords:
# Short terms (2-5 chars) that must match as whole words only.
# Without this, "GAN" would match "organic" or "elegant".
  - MACE
  - MLIP
  - BTE
  - DFT
  - GAN

## Broad keywords:
# Generic terms that only count when a context keyword also appears.
# "thermal conductivity" alone matches too many non-physics papers.
  - thermal conductivity
  - machine learning
  - molecular dynamics

## Context keywords:
# Required co-occurring terms for broad keywords above.
  - phonon
  - lattice
  - first-principles
  - ab initio
  - potential energy surface
  - interatomic potential
"""
