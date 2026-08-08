import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_publications as updater


class PublicationUpdaterTests(unittest.TestCase):
    def test_extracts_plain_and_smart_quoted_titles(self):
        self.assertEqual(updater.title_from('1. T. Ojha, "A Useful Paper Title", IEEE, 2026.'), "A Useful Paper Title")
        self.assertEqual(updater.title_from('1. T. Ojha, “Another Useful Title”, IEEE, 2026.'), "Another Useful Title")

    def test_rejects_under_review_entries(self):
        block = '1. T. Ojha, "An Unpublished Research Paper", _Under Review_, 2026.\n'
        with patch.object(updater, "crossref_match") as lookup:
            unchanged, result = updater.update_block(block, Path("files"))
        self.assertEqual(unchanged, block)
        self.assertEqual(result.status, "skipped")
        lookup.assert_not_called()

    def test_adds_verified_link_and_bibtex(self):
        block = '1. T. Ojha, "A Published Research Paper", _IEEE Example_, 2026.\n'
        metadata = {"DOI": "10.1109/EXAMPLE.2026.123", "title": ["A Published Research Paper"]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(updater, "crossref_match", return_value=(metadata, 1.0)), \
             patch.object(updater, "bibtex_for", return_value="@article{example, title={A Published Research Paper}}"):
            changed, result = updater.update_block(block, Path(directory))
            bib = Path(directory) / updater.bib_filename(metadata["DOI"])
            self.assertTrue(bib.exists())
        self.assertIn("https://doi.org/10.1109/EXAMPLE.2026.123", changed)
        self.assertIn("BibTeX-orange", changed)
        self.assertEqual(result.status, "updated")

    def test_dry_run_does_not_write_bibtex(self):
        block = '1. T. Ojha, "A Published Research Paper", _IEEE Example_, 2026.\n'
        metadata = {"DOI": "10.1109/EXAMPLE.2026.123"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(updater, "crossref_match", return_value=(metadata, 1.0)), \
             patch.object(updater, "bibtex_for", return_value="@article{example}"):
            _, result = updater.update_block(block, Path(directory), dry_run=True)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(result.status, "would update")

    def test_corrects_stale_doi_after_confident_match(self):
        block = ('1. T. Ojha, "A Published Research Paper", _IEEE Example_, 2026.\n'
                 '[![Link](badge)](https://doi.org/10.1109/OLD.1) '
                 '[![BibTeX](https://img.shields.io/badge/BibTeX-orange)](existing.txt)\n')
        metadata = {"DOI": "10.1109/NEW.2"}
        with patch.object(updater, "crossref_match", return_value=(metadata, 1.0)):
            changed, result = updater.update_block(block, Path("files"))
        self.assertIn("https://doi.org/10.1109/NEW.2", changed)
        self.assertNotIn("10.1109/OLD.1", changed)
        self.assertEqual(result.status, "updated")


if __name__ == "__main__":
    unittest.main()
