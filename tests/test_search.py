from __future__ import annotations

import unittest

from unittest.mock import Mock, patch

from app.search import _score_value, _weights, apply_reranker, compare_pipelines


class SearchTests(unittest.TestCase):
    def test_hybrid_weights_are_normalized(self) -> None:
        vector, lexical = _weights()
        self.assertAlmostEqual(vector + lexical, 1.0)
        self.assertAlmostEqual(vector, 0.65)

    def test_score_value_supports_atlas_score_details(self) -> None:
        self.assertEqual(_score_value(0.75), 0.75)
        self.assertEqual(_score_value({"value": 0.125}), 0.125)
        self.assertIsNone(_score_value({"description": "missing"}))

    @patch("app.search.rerank_documents")
    def test_reranker_reorders_candidates_and_keeps_original_score(self, rerank) -> None:
        rerank.return_value = [
            {"index": 1, "relevance_score": 0.91},
            {"index": 0, "relevance_score": 0.72},
        ]
        candidates = [
            {"_id": "first", "text": "first result", "score": 0.8},
            {"_id": "second", "text": "second result", "score": 0.7},
        ]
        ranked = apply_reranker("question", candidates, 2)
        self.assertEqual([item["_id"] for item in ranked], ["second", "first"])
        self.assertEqual(ranked[0]["score"], 0.7)
        self.assertEqual(ranked[0]["rerank_score"], 0.91)

    @patch("app.search.run_pipeline")
    @patch("app.search.get_collection")
    def test_comparison_runs_only_vector_lanes_available_on_source(
        self, collection_factory, run_pipeline
    ) -> None:
        collection_factory.return_value.find_one.return_value = {
            "embedding_voyage_4_lite": [0.1],
            "embedding_voyage_multimodal_3_5": [0.2],
        }
        run_pipeline.side_effect = lambda _q, _s, _m, lane, _l, _r: {"key": lane}

        rows = compare_pipelines("question", "source-123", "vector", 5)

        self.assertEqual(
            [row["key"] for row in rows],
            ["voyage_4_lite", "voyage_multimodal_3_5"],
        )


if __name__ == "__main__":
    unittest.main()
