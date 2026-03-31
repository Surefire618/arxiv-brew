"""Tests for the keyword filtering engine."""


from arxiv_brew.arxiv_api import Paper
from arxiv_brew.config import FilterConfig
from arxiv_brew.filter import match_clusters, keyword_filter


def _make_paper(title: str, abstract: str = "", arxiv_id: str = "2603.00001") -> Paper:
    return Paper(
        id=arxiv_id, title=title, authors=["A. Test"],
        abstract=abstract, published="2026-03-31", updated="2026-03-31",
        categories=["cond-mat.mtrl-sci"], primary_category="cond-mat.mtrl-sci",
    )


class TestMatchClusters:
    def test_exact_keyword_match(self):
        p = _make_paper("Lattice thermal conductivity of silicon from first principles")
        clusters = match_clusters(p, FilterConfig())
        assert "Transport Methods" in clusters

    def test_acronym_word_boundary(self):
        """MACE should not match 'prevalence' or 'pharmaceutical'."""
        p = _make_paper("Prevalence of pharmaceutical contaminants")
        clusters = match_clusters(p, FilterConfig())
        assert clusters == []

    def test_acronym_real_match(self):
        p = _make_paper("Training MACE potentials for molecular dynamics")
        clusters = match_clusters(p, FilterConfig())
        assert "ML for Atomistic Modeling" in clusters

    def test_broad_keyword_needs_context(self):
        """'thermal conductivity' without atomistic context should not match."""
        p = _make_paper("Thermal conductivity of concrete in building insulation")
        clusters = match_clusters(p, FilterConfig())
        assert clusters == []

    def test_broad_keyword_with_context(self):
        p = _make_paper(
            "Thermal conductivity of perovskites",
            abstract="We compute phonon transport using DFT-based methods."
        )
        clusters = match_clusters(p, FilterConfig())
        assert "Transport Methods" in clusters

    def test_multiple_clusters(self):
        p = _make_paper(
            "Anharmonic lattice thermal conductivity",
            abstract="Using phonon-phonon interaction and Green-Kubo method in crystals."
        )
        clusters = match_clusters(p, FilterConfig())
        assert len(clusters) >= 2

    def test_no_match(self):
        p = _make_paper("Superconducting vortex dynamics in cuprates")
        clusters = match_clusters(p, FilterConfig())
        assert clusters == []

    def test_case_insensitive(self):
        p = _make_paper("NEURAL NETWORK POTENTIAL FOR SILICON")
        clusters = match_clusters(p, FilterConfig())
        assert "ML for Atomistic Modeling" in clusters


class TestKeywordFilter:
    def test_filters_and_populates_clusters(self):
        papers = [
            _make_paper("MACE potential for water", arxiv_id="2603.00001"),
            _make_paper("Political science review", arxiv_id="2603.00002"),
            _make_paper("Phonon transport in SrTiO3 from lattice dynamics", arxiv_id="2603.00003"),
        ]
        config = FilterConfig()
        filtered = keyword_filter(papers, config)
        assert len(filtered) == 2
        assert filtered[0].matched_clusters
        assert filtered[1].matched_clusters
