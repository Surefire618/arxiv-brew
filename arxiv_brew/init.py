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
# This file defines your arxiv-brew keywords. Edit the sections below.
# Then run: arxiv-brew --research-profile config/my_research.md --init-keywords --digest-only

## Categories:
# arXiv categories to scan daily.
# Full list: https://arxiv.org/category_taxonomy
  - cs.CL
  - cs.AI

## Natural Language Processing:
  - language model
  - transformer architecture
  - attention mechanism
  - machine translation
  - text generation
  - named entity recognition
  - sentiment analysis
  - question answering
  - BERT
  - GPT

## Reinforcement Learning:
  - reinforcement learning
  - policy gradient
  - reward model
  - RLHF
  - multi-agent

## Word boundary keywords:
# Short terms that must match as whole words only.
# Example: "GAN" listed here won't match "organic" or "elegant".
  - BERT
  - GPT
  - GAN
  - RLHF

## Broad keywords:
# Generic terms that only count when a context keyword also appears.
  - language model
  - attention mechanism

## Context keywords:
# Required co-occurring terms for broad keywords.
  - neural
  - training
  - benchmark
  - dataset
  - fine-tuning
  - pre-training
"""
