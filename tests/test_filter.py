"""Tests for the keyword filtering and scoring engine."""

import unittest

from arxiv_brew.arxiv_api import Paper
from arxiv_brew.config import FilterConfig
from arxiv_brew.filter import score_paper, keyword_filter


def _config():
    return FilterConfig(
        topic_clusters={
            "ML Potentials": ["neural network potential", "MACE", "MLIP", "deep potential"],
            "Thermal Transport": ["thermal conductivity", "Green-Kubo", "phonon transport"],
        },
        word_boundary_keywords={"MACE", "MLIP"},
        broad_keywords={"thermal conductivity"},
        context_keywords=["phonon", "lattice", "DFT", "first-principles", "perovskite"],
    )


def _p(title, abstract="", arxiv_id="2603.00001"):
    return Paper(
        id=arxiv_id, title=title, authors=["A. Test"],
        abstract=abstract, published="2026-03-31", updated="2026-03-31",
        categories=["cond-mat.mtrl-sci"], primary_category="cond-mat.mtrl-sci",
    )


class TestScorePaper(unittest.TestCase):
    def test_exact_keyword_match(self):
        clusters, score = score_paper(
            _p("Phonon transport in silicon from Green-Kubo"), _config())
        self.assertIn("Thermal Transport", clusters)
        self.assertGreater(score, 0)

    def test_acronym_word_boundary_no_false_positive(self):
        clusters, score = score_paper(
            _p("Prevalence of pharmaceutical contaminants"), _config())
        self.assertEqual(clusters, [])
        self.assertEqual(score, 0)

    def test_acronym_real_match(self):
        clusters, score = score_paper(
            _p("Training MACE potentials for molecular dynamics"), _config())
        self.assertIn("ML Potentials", clusters)

    def test_broad_keyword_needs_context(self):
        clusters, _ = score_paper(
            _p("Thermal conductivity of concrete in building insulation"), _config())
        self.assertEqual(clusters, [])

    def test_broad_keyword_with_context(self):
        clusters, _ = score_paper(
            _p("Thermal conductivity of perovskite", "phonon DFT calculation"), _config())
        self.assertIn("Thermal Transport", clusters)

    def test_no_match(self):
        clusters, score = score_paper(
            _p("Superconducting vortex dynamics in cuprates"), _config())
        self.assertEqual(clusters, [])
        self.assertEqual(score, 0)

    def test_empty_config(self):
        clusters, score = score_paper(_p("Anything at all"), FilterConfig())
        self.assertEqual(clusters, [])

    def test_title_scores_higher_than_abstract(self):
        """Same keyword in title should score higher than in abstract."""
        _, title_score = score_paper(
            _p("MACE potential for water"), _config())
        _, abstract_score = score_paper(
            _p("A study of potentials", abstract="MACE potential for water"), _config())
        self.assertGreater(title_score, abstract_score)

    def test_multiple_keyword_hits_increase_score(self):
        """Hitting more keywords in a cluster should increase score."""
        _, single_score = score_paper(
            _p("MACE potential"), _config())
        _, multi_score = score_paper(
            _p("MACE and MLIP deep potential neural network potential"), _config())
        self.assertGreater(multi_score, single_score)

    def test_multi_cluster_bonus(self):
        """Papers matching multiple clusters get a bonus."""
        clusters, score = score_paper(
            _p("MACE potential with phonon transport",
               abstract="Green-Kubo thermal conductivity with DFT"), _config())
        self.assertGreater(len(clusters), 1)
        # Score should include the multi-cluster bonus
        self.assertGreater(score, 5.0)


class TestKeywordFilter(unittest.TestCase):
    def test_filters_and_populates_clusters(self):
        papers = [
            _p("MACE potential for water", arxiv_id="1"),
            _p("Political science review", arxiv_id="2"),
        ]
        filtered = keyword_filter(papers, _config())
        self.assertEqual(len(filtered), 1)
        self.assertTrue(filtered[0].matched_clusters)
        self.assertGreater(filtered[0].relevance_score, 0)

    def test_results_sorted_by_score(self):
        papers = [
            _p("A study of potentials", abstract="MACE is used", arxiv_id="1"),
            _p("MACE and MLIP deep potential neural network potential", arxiv_id="2"),
        ]
        filtered = keyword_filter(papers, _config())
        self.assertEqual(len(filtered), 2)
        self.assertGreaterEqual(filtered[0].relevance_score, filtered[1].relevance_score)


if __name__ == "__main__":
    unittest.main()
