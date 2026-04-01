"""Tests for keyword management: update, add, remove, reset."""

import os
import tempfile
import unittest

from arxiv_brew.keywords import KeywordDB


PROFILE_V1 = """\
## Categories:
  - cs.CL

## NLP:
  - transformer
  - attention mechanism
  - BERT

## Word boundary keywords:
  - BERT

## Broad keywords:
  - attention mechanism

## Context keywords:
  - neural
"""

PROFILE_V2 = """\
## Categories:
  - cs.CL
  - cs.AI

## NLP:
  - transformer
  - language model

## Word boundary keywords:
  - BERT

## Broad keywords:
  - language model

## Context keywords:
  - neural
  - training
"""


class TestUpdateFromProfile(unittest.TestCase):
    def _db(self, d):
        return KeywordDB(os.path.join(d, "kw.json"))

    def _write(self, d, content, name="profile.md"):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write(content)
        return p

    def test_initial_update(self):
        with tempfile.TemporaryDirectory() as d:
            db = self._db(d)
            prof = self._write(d, PROFILE_V1)
            result = db.update_from_profile(prof)
            self.assertEqual(result["added"], 3)
            self.assertEqual(result["removed"], 0)

    def test_add_new_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            db = self._db(d)
            prof = self._write(d, PROFILE_V1)
            db.update_from_profile(prof)
            # V2 adds "language model", removes "attention mechanism" and "BERT"
            prof = self._write(d, PROFILE_V2)
            result = db.update_from_profile(prof)
            self.assertEqual(result["added"], 1)  # "language model"
            self.assertEqual(result["removed"], 2)  # "attention mechanism", "BERT"

    def test_llm_keywords_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            db = self._db(d)
            prof = self._write(d, PROFILE_V1)
            db.update_from_profile(prof)
            # LLM adds a keyword
            db.learn_keywords([{"keyword": "GPT-4", "cluster": "NLP"}])
            # Update with V2 (removes some user keywords)
            prof = self._write(d, PROFILE_V2)
            db.update_from_profile(prof)
            # GPT-4 should still be there
            config = db.to_filter_config()
            self.assertIn("GPT-4", config.topic_clusters["NLP"])

    def test_categories_updated(self):
        with tempfile.TemporaryDirectory() as d:
            db = self._db(d)
            prof = self._write(d, PROFILE_V1)
            db.update_from_profile(prof)
            self.assertEqual(db.to_filter_config().categories, ["cs.CL"])
            prof = self._write(d, PROFILE_V2)
            db.update_from_profile(prof)
            self.assertEqual(db.to_filter_config().categories, ["cs.CL", "cs.AI"])


class TestResetFromProfile(unittest.TestCase):
    def test_reset_discards_llm(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            prof = os.path.join(d, "p.md")
            with open(prof, "w") as f:
                f.write(PROFILE_V1)
            db.update_from_profile(prof)
            db.learn_keywords([{"keyword": "GPT-4", "cluster": "NLP"}])
            self.assertIn("GPT-4", db.to_filter_config().topic_clusters["NLP"])
            db.reset_from_profile(prof)
            self.assertNotIn("GPT-4", db.to_filter_config().topic_clusters["NLP"])


class TestAddRemoveKeyword(unittest.TestCase):
    def test_add_new(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            self.assertTrue(db.add_keyword("NLP", "transformer"))
            self.assertIn("transformer", db.to_filter_config().topic_clusters["NLP"])

    def test_add_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.add_keyword("NLP", "transformer")
            self.assertFalse(db.add_keyword("NLP", "transformer"))

    def test_remove(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.add_keyword("NLP", "transformer")
            self.assertTrue(db.remove_keyword("NLP", "transformer"))
            self.assertNotIn("transformer", db.to_filter_config().topic_clusters.get("NLP", []))

    def test_remove_nonexistent(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            self.assertFalse(db.remove_keyword("NLP", "nonexistent"))


class TestListKeywords(unittest.TestCase):
    def test_list(self):
        with tempfile.TemporaryDirectory() as d:
            db = KeywordDB(os.path.join(d, "kw.json"))
            db.add_keyword("NLP", "transformer")
            db.add_keyword("NLP", "attention")
            result = db.list_keywords()
            self.assertEqual(len(result["NLP"]), 2)
            kws = {item["keyword"] for item in result["NLP"]}
            self.assertEqual(kws, {"transformer", "attention"})


if __name__ == "__main__":
    unittest.main()
