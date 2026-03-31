"""Tests for the keyword database."""

import os
import tempfile
import unittest

from arxiv_brew.keywords import KeywordDB


SAMPLE_PROFILE = """\
# My Research

## Categories:
  - cs.CL
  - cs.AI

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


def _write_profile(d, content):
    path = os.path.join(d, "research.md")
    with open(path, "w") as f:
        f.write(content)
    return path


class TestKeywordDB(unittest.TestCase):
    def test_init_from_profile(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            stats = db.stats()
            self.assertEqual(stats["total_keywords"], 4)
            self.assertEqual(stats["by_source"]["user"], 4)

    def test_categories_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            config = db.to_filter_config()
            self.assertEqual(config.categories, ["cs.CL", "cs.AI"])

    def test_no_profile_stays_empty(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            self.assertEqual(db.stats()["total_keywords"], 0)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            count1 = db.stats()["total_keywords"]
            db.init_from_profile(prof)  # should not re-init
            self.assertEqual(db.stats()["total_keywords"], count1)

    def test_word_boundary_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            config = db.to_filter_config()
            self.assertIn("KW3", config.word_boundary_keywords)

    def test_broad_and_context_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            config = db.to_filter_config()
            self.assertIn("keyword one", config.broad_keywords)
            self.assertIn("context word", config.context_keywords)

    def test_learn_keywords(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            before = db.stats()["total_keywords"]
            added = db.learn_keywords([
                {"keyword": "new term", "cluster": "Topic A", "reason": "test"},
            ])
            self.assertEqual(added, 1)
            self.assertEqual(db.stats()["total_keywords"], before + 1)
            self.assertEqual(db.stats()["by_source"].get("llm"), 1)

    def test_learn_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            prof = _write_profile(d, SAMPLE_PROFILE)
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.init_from_profile(prof)
            db.learn_keywords([{"keyword": "new term", "cluster": "Topic A"}])
            before = db.stats()["total_keywords"]
            db.learn_keywords([{"keyword": "new term", "cluster": "Topic A"}])
            self.assertEqual(db.stats()["total_keywords"], before)


if __name__ == "__main__":
    unittest.main()
