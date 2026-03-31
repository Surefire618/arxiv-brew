"""Tests for arXiv API parsing."""

import xml.etree.ElementTree as ET


from arxiv_brew.arxiv_api import Paper, _parse_entry


_SAMPLE_ENTRY = """\
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <id>http://arxiv.org/abs/2603.28267v1</id>
  <title>Intrinsically ultralow thermal conductivity in all-inorganic superatomic bulk crystals</title>
  <summary>Superatomic compounds exhibit large anharmonicity vibrations.</summary>
  <published>2026-03-30T10:50:35Z</published>
  <updated>2026-03-30T10:50:35Z</updated>
  <author><name>Mingzhang Yang</name></author>
  <author><name>Jian-Gang Guo</name></author>
  <category term="cond-mat.mtrl-sci" scheme="http://arxiv.org/schemas/atom"/>
  <category term="cond-mat.stat-mech" scheme="http://arxiv.org/schemas/atom"/>
  <arxiv:primary_category term="cond-mat.mtrl-sci" scheme="http://arxiv.org/schemas/atom"/>
</entry>
"""


class TestParseEntry:
    def test_basic_fields(self):
        root = ET.fromstring(_SAMPLE_ENTRY)
        paper = _parse_entry(root)
        assert paper.id == "2603.28267"
        assert "ultralow thermal conductivity" in paper.title
        assert paper.authors == ["Mingzhang Yang", "Jian-Gang Guo"]
        assert paper.published == "2026-03-30"
        assert "cond-mat.mtrl-sci" in paper.categories
        assert paper.primary_category == "cond-mat.mtrl-sci"

    def test_urls_auto_generated(self):
        root = ET.fromstring(_SAMPLE_ENTRY)
        paper = _parse_entry(root)
        assert paper.abs_url == "https://arxiv.org/abs/2603.28267"
        assert paper.html_url == "https://arxiv.org/html/2603.28267v1"
        assert paper.pdf_url == "https://arxiv.org/pdf/2603.28267.pdf"


class TestPaperSerialization:
    def test_roundtrip(self):
        p = Paper(
            id="2603.00001", title="Test Paper", authors=["A. Test"],
            abstract="Abstract text.", published="2026-03-31", updated="2026-03-31",
            categories=["cond-mat.mtrl-sci"], primary_category="cond-mat.mtrl-sci",
            matched_clusters=["Transport Methods"],
        )
        d = p.to_dict()
        p2 = Paper.from_dict(d)
        assert p2.id == p.id
        assert p2.title == p.title
        assert p2.matched_clusters == p.matched_clusters
