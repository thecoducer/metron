"""Unit tests for app/api/entity_matcher.py."""

import unittest
from unittest.mock import patch

import numpy as np

from app.api.entity_matcher import EntityMatcher, _preprocess_for_embedding


class TestPreprocessForEmbedding(unittest.TestCase):
    """Tests for _preprocess_for_embedding helper."""

    def test_strips_date_suffix(self):
        self.assertEqual(
            _preprocess_for_embedding("HDFC Bank Limited (24/06/2026)"),
            "HDFC Bank",
        )

    def test_strips_ltd_dot(self):
        self.assertEqual(
            _preprocess_for_embedding("HDFC Bank Ltd."),
            "HDFC Bank",
        )

    def test_strips_limited(self):
        self.assertEqual(
            _preprocess_for_embedding("Infosys Limited"),
            "Infosys",
        )

    def test_strips_pvt_ltd(self):
        self.assertEqual(
            _preprocess_for_embedding("ABC Pvt. Ltd."),
            "ABC",
        )

    def test_strips_private_limited(self):
        self.assertEqual(
            _preprocess_for_embedding("XYZ Private Limited"),
            "XYZ",
        )

    def test_strips_incorporated(self):
        self.assertEqual(
            _preprocess_for_embedding("Foo Inc."),
            "Foo",
        )

    def test_preserves_core_name(self):
        self.assertEqual(
            _preprocess_for_embedding("Infosys"),
            "Infosys",
        )

    def test_collapses_whitespace(self):
        self.assertEqual(
            _preprocess_for_embedding("HDFC  Bank   Limited"),
            "HDFC Bank",
        )

    def test_date_with_single_digit_day(self):
        self.assertEqual(
            _preprocess_for_embedding("SBI Bank (1/06/2026)"),
            "SBI Bank",
        )


class TestEntityMatcherCluster(unittest.TestCase):
    """Tests for EntityMatcher.cluster_names with a mocked model."""

    def _make_matcher(self, sim_matrix: np.ndarray) -> EntityMatcher:
        """Build an EntityMatcher with a mocked MiniLM model.

        The mock ``_encode`` returns pre-computed vectors whose
        pairwise dot products reproduce *sim_matrix*.
        """

        def fake_encode(texts: list[str]) -> np.ndarray:
            n = len(texts)
            return sim_matrix[:n]

        with patch.object(EntityMatcher, "__init__", lambda self, **kw: None):
            matcher = EntityMatcher()
            matcher.threshold = 0.75
            matcher._encode = fake_encode  # type: ignore[assignment]
        return matcher

    def test_empty_input(self):
        matcher = self._make_matcher(np.array([]))
        result = matcher.cluster_names([])
        self.assertEqual(result, {})

    def test_single_input(self):
        matcher = self._make_matcher(np.array([[1.0]]))
        result = matcher.cluster_names(["HDFC Bank"])
        self.assertEqual(result, {"HDFC Bank": "HDFC Bank"})

    def test_similar_names_cluster(self):
        # Two names with high similarity (0.9) should cluster.
        # Use normalized vectors so dot product gives the similarity.
        vecs = np.array(
            [
                [1.0, 0.0],
                [0.9, np.sqrt(1 - 0.81)],  # cos sim ≈ 0.9 with first
            ]
        )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs_norm = vecs / norms
        matcher = self._make_matcher(vecs_norm)

        result = matcher.cluster_names(["HDFC Bank", "HDFC Bank Limited"])
        # Both should map to the longer name.
        self.assertEqual(len(set(result.values())), 1)
        self.assertEqual(result["HDFC Bank"], "HDFC Bank Limited")
        self.assertEqual(result["HDFC Bank Limited"], "HDFC Bank Limited")

    def test_different_names_separate(self):
        # Two names with low similarity (0.1) should stay separate.
        vecs = np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],  # orthogonal → cos sim = 0
            ]
        )
        matcher = self._make_matcher(vecs)

        result = matcher.cluster_names(["HDFC Bank", "Tata Steel"])
        self.assertEqual(len(set(result.values())), 2)
        self.assertEqual(result["HDFC Bank"], "HDFC Bank")
        self.assertEqual(result["Tata Steel"], "Tata Steel")

    def test_transitive_clustering(self):
        # A-B similar, B-C similar → all three should cluster.
        # Use 3D vectors where A·B ≈ 0.8, B·C ≈ 0.8, A·C ≈ 0.64
        vecs = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.85, 0.52, 0.0],  # high sim with A
                [0.72, 0.69, 0.06],  # high sim with B
            ]
        )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs_norm = vecs / norms
        matcher = self._make_matcher(vecs_norm)

        result = matcher.cluster_names(["A Short", "B Medium Name", "C Longest Name Here"])
        # All should cluster; canonical = longest.
        canonical_values = set(result.values())
        self.assertEqual(len(canonical_values), 1)
        self.assertEqual(result["A Short"], "C Longest Name Here")


if __name__ == "__main__":
    unittest.main()
