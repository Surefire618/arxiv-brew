"""Tests for cross-day deduplication via SeenIndex."""

import json
import os
import tempfile
import unittest

from arxiv_brew.db import SeenIndex


class TestSeenIndex(unittest.TestCase):
    def test_mark_and_contains(self):
        with tempfile.TemporaryDirectory() as d:
            idx = SeenIndex(os.path.join(d, "seen.json"))
            self.assertNotIn("2603.00001", idx)
            idx.mark_seen(["2603.00001", "2603.00002"])
            self.assertIn("2603.00001", idx)
            self.assertIn("2603.00002", idx)
            self.assertNotIn("2603.99999", idx)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seen.json")
            idx = SeenIndex(path)
            idx.mark_seen(["2603.00001"])
            idx.save()

            idx2 = SeenIndex(path)
            self.assertIn("2603.00001", idx2)

    def test_no_duplicate_on_remark(self):
        with tempfile.TemporaryDirectory() as d:
            idx = SeenIndex(os.path.join(d, "seen.json"))
            idx.mark_seen(["2603.00001"])
            idx.mark_seen(["2603.00001"])
            self.assertEqual(len(idx), 1)

    def test_prune_removes_old(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seen.json")
            # Manually write old entries
            data = {"2603.00001": "2020-01-01", "2603.00002": "2099-12-31"}
            with open(path, "w") as f:
                json.dump(data, f)
            idx = SeenIndex(path)
            idx.prune(retention_days=90)
            self.assertNotIn("2603.00001", idx)
            self.assertIn("2603.00002", idx)

    def test_empty_file_handled(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seen.json")
            idx = SeenIndex(path)
            self.assertEqual(len(idx), 0)


if __name__ == "__main__":
    unittest.main()
