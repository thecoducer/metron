"""Unit tests for the company classifier module (app/api/company_classifier.py)."""

import unittest
from unittest.mock import MagicMock, patch


class TestCompanyClassifier(unittest.TestCase):
    """Tests for CompanyClassifier with a mocked transformers pipeline."""

    def _make_classifier(self):
        """Build a CompanyClassifier with a mocked pipeline."""
        with patch("transformers.pipeline") as mock_pipeline_fn:
            mock_pipe = MagicMock()
            mock_pipeline_fn.return_value = mock_pipe
            from app.api.company_classifier import CompanyClassifier

            classifier = CompanyClassifier()
        classifier._pipeline = mock_pipe
        return classifier

    def test_classify_returns_top_label(self):
        classifier = self._make_classifier()
        classifier._pipeline.return_value = {
            "labels": ["Banking", "Insurance", "IT Services"],
            "scores": [0.95, 0.03, 0.02],
        }
        label, score = classifier.classify("HDFC Bank Limited")
        self.assertEqual(label, "Banking")
        self.assertAlmostEqual(score, 0.95)

    def test_classify_caches_results(self):
        classifier = self._make_classifier()
        classifier._pipeline.return_value = {
            "labels": ["Insurance"],
            "scores": [0.90],
        }
        classifier.classify("HDFC Life Insurance")
        classifier.classify("HDFC Life Insurance")
        # Pipeline called only once — second call served from cache.
        classifier._pipeline.assert_called_once()

    def test_classify_batch_groups_results(self):
        classifier = self._make_classifier()
        classifier._pipeline.return_value = [
            {"labels": ["Banking", "Insurance"], "scores": [0.96, 0.02]},
            {"labels": ["IT Services", "Banking"], "scores": [0.92, 0.04]},
        ]
        results = classifier.classify_batch(["HDFC Bank", "Infosys"])
        self.assertEqual(results["HDFC Bank"], ("Banking", 0.96))
        self.assertEqual(results["Infosys"], ("IT Services", 0.92))

    def test_classify_batch_uses_cache(self):
        classifier = self._make_classifier()
        # Pre-populate cache.
        classifier._cache["HDFC Bank"] = ("Banking", 0.96)
        classifier._pipeline.return_value = [
            {"labels": ["IT Services"], "scores": [0.92]},
        ]
        results = classifier.classify_batch(["HDFC Bank", "Infosys"])
        self.assertEqual(results["HDFC Bank"], ("Banking", 0.96))
        self.assertEqual(results["Infosys"], ("IT Services", 0.92))
        # Only "Infosys" was sent to the pipeline.
        classifier._pipeline.assert_called_once()
        self.assertEqual(classifier._pipeline.call_args[0][0], ["Infosys"])

    def test_classify_batch_single_item(self):
        """Pipeline returns a dict (not list) for a single item."""
        classifier = self._make_classifier()
        classifier._pipeline.return_value = {
            "labels": ["Pharmaceuticals"],
            "scores": [0.85],
        }
        results = classifier.classify_batch(["Sun Pharma"])
        self.assertEqual(results["Sun Pharma"], ("Pharmaceuticals", 0.85))

    def test_classify_batch_all_cached(self):
        classifier = self._make_classifier()
        classifier._cache["A"] = ("Banking", 0.9)
        classifier._cache["B"] = ("Insurance", 0.8)
        results = classifier.classify_batch(["A", "B"])
        self.assertEqual(results["A"], ("Banking", 0.9))
        self.assertEqual(results["B"], ("Insurance", 0.8))
        # Pipeline never called.
        classifier._pipeline.assert_not_called()

    def test_classify_with_custom_labels(self):
        classifier = self._make_classifier()
        classifier._pipeline.return_value = {
            "labels": ["Fintech"],
            "scores": [0.88],
        }
        label, score = classifier.classify("Paytm", labels=["Fintech", "Banking"])
        self.assertEqual(label, "Fintech")
        self.assertAlmostEqual(score, 0.88)


if __name__ == "__main__":
    unittest.main()
