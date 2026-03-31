"""Tests for affiliation extraction and digest formatting."""

import unittest

from arxiv_brew.summarize import (
    extract_affiliations,
    extract_corresponding_author,
    format_digest,
)


class TestExtractAffiliations(unittest.TestCase):
    def test_organization_tag(self):
        content = 'organization=MIT, organization=Stanford University\n' + 'x' * 500
        affs = extract_affiliations(content)
        self.assertIn("MIT", affs)
        self.assertIn("Stanford University", affs)

    def test_institution_names(self):
        content = (
            "Department of Physics, University of California, Berkeley\n"
            "Max Planck Institute for Solid State Research\n"
            + "x" * 500
        )
        affs = extract_affiliations(content)
        self.assertTrue(any("University of California" in a for a in affs))
        self.assertTrue(any("Max Planck" in a for a in affs))

    def test_no_affiliations(self):
        content = "This is a paper about physics.\n" + "x" * 500
        affs = extract_affiliations(content)
        self.assertEqual(affs, [])

    def test_deduplication(self):
        content = (
            "organization=MIT, organization=MIT, organization=MIT\n" + "x" * 500
        )
        affs = extract_affiliations(content)
        self.assertEqual(affs.count("MIT"), 1)

    def test_max_five(self):
        content = "\n".join(
            f"organization=University {i}" for i in range(10)
        ) + "\n" + "x" * 500
        affs = extract_affiliations(content)
        self.assertLessEqual(len(affs), 5)


class TestExtractCorrespondingAuthor(unittest.TestCase):
    def test_explicit_corresponding(self):
        content = "Corresponding author: John Smith\n" + "x" * 500
        result = extract_corresponding_author(content, ["Alice Bob", "John Smith"])
        self.assertEqual(result, "John Smith")

    def test_email_match(self):
        content = "Contact: smith@uni.edu\n" + "x" * 500
        result = extract_corresponding_author(content, ["Alice Bob", "John Smith"])
        self.assertEqual(result, "John Smith")

    def test_fallback_last_author(self):
        content = "No contact info here.\n" + "x" * 500
        result = extract_corresponding_author(content, ["Alice", "Bob"])
        self.assertEqual(result, "Bob")

    def test_empty_authors(self):
        content = "No contact info here.\n" + "x" * 500
        result = extract_corresponding_author(content, [])
        self.assertIsNone(result)


class TestFormatDigest(unittest.TestCase):
    def test_groups_by_cluster(self):
        summaries = [
            {"id": "1", "title": "Paper A", "authors_full": "A",
             "affiliation_str": "", "abs_url": "", "matched_clusters": ["ML"],
             "relevance_score": 3.0, "abstract": "abs",
             "summary_background": "", "summary_contribution": "",
             "summary_significance": ""},
            {"id": "2", "title": "Paper B", "authors_full": "B",
             "affiliation_str": "", "abs_url": "", "matched_clusters": ["Physics"],
             "relevance_score": 1.0, "abstract": "abs",
             "summary_background": "", "summary_contribution": "",
             "summary_significance": ""},
        ]
        digest = format_digest("2026-04-01", summaries)
        self.assertIn("**ML**", digest)
        self.assertIn("**Physics**", digest)
        self.assertIn("Paper A", digest)
        self.assertIn("Paper B", digest)

    def test_no_duplicates_across_clusters(self):
        summaries = [
            {"id": "1", "title": "Paper A", "authors_full": "A",
             "affiliation_str": "", "abs_url": "", "matched_clusters": ["ML", "Physics"],
             "relevance_score": 5.0, "abstract": "abs",
             "summary_background": "", "summary_contribution": "",
             "summary_significance": ""},
        ]
        digest = format_digest("2026-04-01", summaries)
        self.assertEqual(digest.count("Paper A"), 1)

    def test_score_in_digest(self):
        summaries = [
            {"id": "1", "title": "Paper A", "authors_full": "A",
             "affiliation_str": "", "abs_url": "", "matched_clusters": ["ML"],
             "relevance_score": 4.5, "abstract": "abs",
             "summary_background": "", "summary_contribution": "",
             "summary_significance": ""},
        ]
        digest = format_digest("2026-04-01", summaries)
        self.assertIn("score: 4.5", digest)


if __name__ == "__main__":
    unittest.main()
