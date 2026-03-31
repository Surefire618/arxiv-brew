"""Tests for the keyword filtering engine."""

import unittest

from arxiv_brew.arxiv_api import Paper
from arxiv_brew.config import FilterConfig
from arxiv_brew.filter import match_clusters, keyword_filter


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


class TestMatchClusters(unittest.TestCase):
    def test_exact_keyword_match(self):
        self.assertIn("Thermal Transport", match_clusters(_p("Phonon transport in silicon from Green-Kubo"), _config()))

    def test_acronym_word_boundary_no_false_positive(self):
        self.assertEqual(match_clusters(_p("Prevalence of pharmaceutical contaminants"), _config()), [])

    def test_acronym_real_match(self):
        self.assertIn("ML Potentials", match_clusters(_p("Training MACE potentials for molecular dynamics"), _config()))

    def test_broad_keyword_needs_context(self):
        self.assertEqual(match_clusters(_p("Thermal conductivity of concrete in building insulation"), _config()), [])

    def test_broad_keyword_with_context(self):
        self.assertIn("Thermal Transport", match_clusters(_p("Thermal conductivity of perovskite", "phonon DFT calculation"), _config()))

    def test_no_match(self):
        self.assertEqual(match_clusters(_p("Superconducting vortex dynamics in cuprates"), _config()), [])

    def test_empty_config(self):
        self.assertEqual(match_clusters(_p("Anything at all"), FilterConfig()), [])


class TestKeywordFilter(unittest.TestCase):
    def test_filters_and_populates_clusters(self):
        papers = [
            _p("MACE potential for water", arxiv_id="1"),
            _p("Political science review", arxiv_id="2"),
        ]
        filtered = keyword_filter(papers, _config())
        self.assertEqual(len(filtered), 1)
        self.assertTrue(filtered[0].matched_clusters)


if __name__ == "__main__":
    unittest.main()
