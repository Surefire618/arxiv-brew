"""Tests for the keyword filtering engine."""

from arxiv_brew.arxiv_api import Paper
from arxiv_brew.config import FilterConfig
from arxiv_brew.filter import match_clusters, keyword_filter


def _config():
    """A sample config for testing (not hardcoded in the package)."""
    return FilterConfig(
        topic_clusters={
            "ML Potentials": ["neural network potential", "MACE", "MLIP", "deep potential"],
            "Thermal Transport": ["thermal conductivity", "Green-Kubo", "phonon transport"],
        },
        word_boundary_keywords={"MACE", "MLIP"},
        broad_keywords={"thermal conductivity"},
        context_keywords=["phonon", "lattice", "DFT", "first-principles", "perovskite"],
    )


def _make_paper(title, abstract="", arxiv_id="2603.00001"):
    return Paper(
        id=arxiv_id, title=title, authors=["A. Test"],
        abstract=abstract, published="2026-03-31", updated="2026-03-31",
        categories=["cond-mat.mtrl-sci"], primary_category="cond-mat.mtrl-sci",
    )


class TestMatchClusters:
    def test_exact_keyword_match(self):
        p = _make_paper("Phonon transport in silicon from Green-Kubo")
        assert "Thermal Transport" in match_clusters(p, _config())

    def test_acronym_word_boundary(self):
        p = _make_paper("Prevalence of pharmaceutical contaminants")
        assert match_clusters(p, _config()) == []

    def test_acronym_real_match(self):
        p = _make_paper("Training MACE potentials for molecular dynamics")
        assert "ML Potentials" in match_clusters(p, _config())

    def test_broad_keyword_needs_context(self):
        p = _make_paper("Thermal conductivity of concrete in building insulation")
        assert match_clusters(p, _config()) == []

    def test_broad_keyword_with_context(self):
        p = _make_paper("Thermal conductivity of perovskite", "phonon DFT calculation")
        assert "Thermal Transport" in match_clusters(p, _config())

    def test_no_match(self):
        p = _make_paper("Superconducting vortex dynamics in cuprates")
        assert match_clusters(p, _config()) == []

    def test_empty_config(self):
        p = _make_paper("Anything at all")
        assert match_clusters(p, FilterConfig()) == []


class TestKeywordFilter:
    def test_filters_and_populates_clusters(self):
        papers = [
            _make_paper("MACE potential for water", arxiv_id="1"),
            _make_paper("Political science review", arxiv_id="2"),
        ]
        filtered = keyword_filter(papers, _config())
        assert len(filtered) == 1
        assert filtered[0].matched_clusters
