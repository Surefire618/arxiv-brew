"""Tests for the keyword database."""

import json
import tempfile
from pathlib import Path


from arxiv_brew.keywords import KeywordDB


class TestKeywordDB:
    def test_bootstrap_defaults(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        stats = db.stats()
        assert stats["total_keywords"] > 50
        assert stats["by_source"]["default"] > 50
        assert (tmp_path / "kw.json").exists()

    def test_bootstrap_with_profile(self, tmp_path):
        profile = tmp_path / "my_research.md"
        profile.write_text(
            "# Research\n"
            "## Research areas:\n"
            "  - Phonon polaritons\n"
            "  - Topological phonon transport\n"
        )
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap(research_profile=profile)
        stats = db.stats()
        assert stats["by_source"].get("user", 0) >= 2

    def test_bootstrap_idempotent(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        count1 = db.stats()["total_keywords"]
        db.bootstrap()  # should not re-bootstrap
        count2 = db.stats()["total_keywords"]
        assert count1 == count2

    def test_bootstrap_force(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        db.bootstrap(force=True)  # should not raise

    def test_learn_keywords(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        before = db.stats()["total_keywords"]

        added = db.learn_keywords([
            {"keyword": "phonon polariton", "cluster": "Transport Methods", "reason": "test"},
            {"keyword": "shift current", "cluster": "Transport Methods", "reason": "test"},
        ])
        assert added == 2
        assert db.stats()["total_keywords"] == before + 2
        assert db.stats()["by_source"].get("llm", 0) == 2

    def test_learn_deduplicates(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        db.learn_keywords([
            {"keyword": "new term", "cluster": "Transport Methods"},
        ])
        before = db.stats()["total_keywords"]
        db.learn_keywords([
            {"keyword": "new term", "cluster": "Transport Methods"},  # duplicate
        ])
        assert db.stats()["total_keywords"] == before

    def test_record_hit(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        db.record_hit("Transport Methods", "thermal conductivity")
        cluster = db.data["clusters"]["Transport Methods"]["keywords"]
        assert cluster["thermal conductivity"]["hits"] == 1

    def test_to_filter_config(self, tmp_path):
        db = KeywordDB(tmp_path / "kw.json")
        db.bootstrap()
        config = db.to_filter_config()
        assert "Transport Methods" in config.topic_clusters
        assert len(config.topic_clusters["Transport Methods"]) > 10

    def test_no_system_files_read(self, tmp_path):
        """KeywordDB should never try to read MEMORY.md or USER.md."""
        db = KeywordDB(tmp_path / "kw.json")
        # bootstrap without any profile — should only use defaults
        db.bootstrap()
        stats = db.stats()
        assert "memory" not in stats["by_source"]
        assert "profile" not in stats["by_source"]
        # Only "default" source
        assert list(stats["by_source"].keys()) == ["default"]
