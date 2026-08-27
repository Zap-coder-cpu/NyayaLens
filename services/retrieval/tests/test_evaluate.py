from __future__ import annotations

import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from evaluate import evaluate_ranking, pairwise_preference_at  # noqa: E402


class RetrievalEvaluationTests(unittest.TestCase):
    def test_unjudged_results_are_unknown_not_false_positives(self) -> None:
        scores = evaluate_ranking(
            ["unknown-a", "relevant", "unknown-b", "unknown-c", "unknown-d"],
            {"id": "sparse", "query": "query", "relevance": {"relevant": 2}},
        )
        self.assertEqual(scores["judgedPrecision@5"], 1.0)
        self.assertEqual(scores["judgedCoverage@5"], 0.2)
        self.assertEqual(scores["unjudgedResults@5"], 4)
        self.assertIsNone(scores["explicitContradictionRateAmongJudged@5"])

    def test_explicit_contradictions_are_measured_only_when_reviewed(self) -> None:
        scores = evaluate_ranking(
            ["contrary", "relevant", "unknown"],
            {
                "id": "contrast",
                "query": "query",
                "relevance": {"relevant": 2},
                "contradictory": ["contrary"],
            },
        )
        self.assertEqual(scores["explicitContradictionRateAmongJudged@5"], 0.5)
        self.assertEqual(scores["explicitContradictionQueryHit@5"], 1.0)

    def test_pairwise_metric_respects_graded_preference(self) -> None:
        accuracy, coverage = pairwise_preference_at(
            ["best", "acceptable", "irrelevant"],
            {"best": 3, "acceptable": 1, "irrelevant": 0},
        )
        self.assertEqual(accuracy, 1.0)
        self.assertEqual(coverage, 1.0)


if __name__ == "__main__":
    unittest.main()
