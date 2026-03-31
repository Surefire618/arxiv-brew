"""Tests for arXiv API parsing.

Uses real paper: Knoop, Purcell, Scheffler, Carbogno,
"Anharmonicity Measure for Materials", PRL 130, 236301 (2023).
https://arxiv.org/abs/2006.14672
"""

import unittest
import xml.etree.ElementTree as ET

from arxiv_brew.arxiv_api import Paper, _parse_entry


_SAMPLE_ENTRY = """\
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <id>http://arxiv.org/abs/2006.14672v2</id>
  <title>Anharmonicity Measure for Materials</title>
  <summary>Theoretical frameworks used to qualitatively and quantitatively describe nuclear dynamics in solids are often based on the harmonic approximation. However, this approximation is known to become inaccurate or to break down completely in many modern functional materials. In this work, we derive and discuss a statistical measure that reliably classifies compounds across temperature regimes and material classes by their degree of anharmonicity.</summary>
  <published>2020-06-25T18:00:00Z</published>
  <updated>2020-10-22T11:42:26Z</updated>
  <author><name>Florian Knoop</name></author>
  <author><name>Thomas A. R. Purcell</name></author>
  <author><name>Matthias Scheffler</name></author>
  <author><name>Christian Carbogno</name></author>
  <category term="cond-mat.mtrl-sci" scheme="http://arxiv.org/schemas/atom"/>
  <category term="physics.comp-ph" scheme="http://arxiv.org/schemas/atom"/>
  <arxiv:primary_category term="cond-mat.mtrl-sci" scheme="http://arxiv.org/schemas/atom"/>
</entry>
"""


class TestParseEntry(unittest.TestCase):
    def setUp(self):
        self.paper = _parse_entry(ET.fromstring(_SAMPLE_ENTRY))

    def test_id(self):
        self.assertEqual(self.paper.id, "2006.14672")

    def test_title(self):
        self.assertEqual(self.paper.title, "Anharmonicity Measure for Materials")

    def test_authors(self):
        self.assertEqual(self.paper.authors, [
            "Florian Knoop",
            "Thomas A. R. Purcell",
            "Matthias Scheffler",
            "Christian Carbogno",
        ])

    def test_dates(self):
        self.assertEqual(self.paper.published, "2020-06-25")
        self.assertEqual(self.paper.updated, "2020-10-22")

    def test_categories(self):
        self.assertIn("cond-mat.mtrl-sci", self.paper.categories)
        self.assertIn("physics.comp-ph", self.paper.categories)
        self.assertEqual(self.paper.primary_category, "cond-mat.mtrl-sci")

    def test_abstract_content(self):
        self.assertIn("anharmonicity", self.paper.abstract.lower())
        self.assertIn("harmonic approximation", self.paper.abstract.lower())

    def test_urls(self):
        self.assertEqual(self.paper.abs_url, "https://arxiv.org/abs/2006.14672")
        self.assertEqual(self.paper.pdf_url, "https://arxiv.org/pdf/2006.14672.pdf")


class TestPaperSerialization(unittest.TestCase):
    def test_roundtrip(self):
        original = _parse_entry(ET.fromstring(_SAMPLE_ENTRY))
        restored = Paper.from_dict(original.to_dict())
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.authors, original.authors)
        self.assertEqual(restored.primary_category, original.primary_category)


if __name__ == "__main__":
    unittest.main()
