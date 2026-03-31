"""Tests for the keyword database."""

import os
import tempfile

from arxiv_brew.keywords import KeywordDB


def _write_profile(d, content):
    path = os.path.join(d, "research.md")
    with open(path, "w") as f:
        f.write(content)
    return path


SAMPLE_PROFILE = """\
# My Research

## Topic A:
  - keyword one
  - keyword two
  - KW3

## Topic B:
  - keyword three

## Word boundary keywords:
  - KW3

## Broad keywords:
  - keyword one

## Context keywords:
  - context word
"""


class TestKeywordDB:
    def test_bootstrap_from_profile(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            stats = db.stats()
            assert stats["total_keywords"] == 4  # keyword one, two, KW3, keyword three
            assert stats["by_source"]["user"] == 4

    def test_bootstrap_without_profile_does_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap()  # no profile
            assert db.stats()["total_keywords"] == 0

    def test_bootstrap_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            count1 = db.stats()["total_keywords"]
            db.bootstrap(research_profile=prof)  # should not re-bootstrap
            assert db.stats()["total_keywords"] == count1

    def test_word_boundary_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            config = db.to_filter_config()
            assert "KW3" in config.word_boundary_keywords

    def test_broad_and_context_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            config = db.to_filter_config()
            assert "keyword one" in config.broad_keywords
            assert "context word" in config.context_keywords

    def test_learn_keywords(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            before = db.stats()["total_keywords"]
            added = db.learn_keywords([
                {"keyword": "new term", "cluster": "Topic A", "reason": "test"},
            ])
            assert added == 1
            assert db.stats()["total_keywords"] == before + 1
            assert db.stats()["by_source"].get("llm") == 1

    def test_learn_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap(research_profile=prof)
            db.learn_keywords([{"keyword": "new term", "cluster": "Topic A"}])
            before = db.stats()["total_keywords"]
            db.learn_keywords([{"keyword": "new term", "cluster": "Topic A"}])
            assert db.stats()["total_keywords"] == before

    def test_no_hardcoded_defaults(self):
        """KeywordDB should have zero keywords without a research profile."""
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.bootstrap()
            assert db.stats()["total_keywords"] == 0
            assert db.stats()["by_source"] == {}
