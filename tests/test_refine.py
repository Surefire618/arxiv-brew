"""Tests for stage 2 refinement CLI and Python API."""

import json
import os
import tempfile
import unittest

from arxiv_brew.refine import refine_papers


def _stage1_json(paper_count=3):
    papers = []
    for i in range(1, paper_count + 1):
        papers.append({
            "id": f"2604.{i:05d}",
            "title": f"Paper {i}",
            "authors": ["Author A"],
            "abstract": f"Abstract for paper {i}",
            "published": "2026-04-01",
            "updated": "2026-04-01",
            "categories": ["cs.AI"],
            "primary_category": "cs.AI",
            "matched_clusters": ["ML"],
            "relevance_score": float(paper_count - i + 1),
        })
    return {"date": "2026-04-01", "summaries": papers}


_LLM_RESPONSE = '''
Here are my decisions:

```json
[
  {"index": 1, "keep": true, "reason": "highly relevant"},
  {"index": 2, "keep": false, "reason": "not relevant"},
  {"index": 3, "keep": true, "reason": "somewhat relevant"}
]
```

New keywords:

```json
{"new_keywords": [{"keyword": "novel term", "cluster": "ML", "reason": "found in paper 1"}]}
```
'''


class TestRefinePapers(unittest.TestCase):
    def test_basic_refinement(self):
        with tempfile.TemporaryDirectory() as d:
            cand_path = os.path.join(d, "stage1.json")
            kw_path = os.path.join(d, "keywords.json")
            with open(cand_path, "w") as f:
                json.dump(_stage1_json(), f)
            with open(kw_path, "w") as f:
                json.dump({"clusters": {}, "last_updated": ""}, f)

            result = refine_papers(cand_path, _LLM_RESPONSE, kw_path)
            self.assertEqual(result["stage1_count"], 3)
            self.assertEqual(result["stage2_count"], 2)
            self.assertIn("2604.00001", result["kept_ids"])
            self.assertIn("2604.00003", result["kept_ids"])
            self.assertNotIn("2604.00002", result["kept_ids"])
            self.assertEqual(result["keywords_learned"], 1)

    def test_empty_llm_response(self):
        with tempfile.TemporaryDirectory() as d:
            cand_path = os.path.join(d, "stage1.json")
            kw_path = os.path.join(d, "keywords.json")
            with open(cand_path, "w") as f:
                json.dump(_stage1_json(), f)
            with open(kw_path, "w") as f:
                json.dump({"clusters": {}, "last_updated": ""}, f)

            result = refine_papers(cand_path, "I don't know", kw_path)
            self.assertEqual(result["stage2_count"], 0)
            self.assertEqual(result["keywords_learned"], 0)


if __name__ == "__main__":
    unittest.main()
