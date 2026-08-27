import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.engine import SemanticEngine
from app.models import SearchFilters


class SemanticEngineSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = SemanticEngine()

    def test_default_bail_query_returns_relevant_source_linked_results(self) -> None:
        response = self.engine.search(
            "The statutory investigation period expired, giving a right to default bail under Section 167(2).",
            SearchFilters(),
            5,
        )
        self.assertTrue(response.results)
        self.assertIn("bail", response.results[0].matchedEvidence.lower())
        self.assertTrue(response.results[0].caseSummary)
        self.assertTrue(response.results[0].trialStatus)
        self.assertTrue(response.results[0].winner)
        self.assertTrue(response.results[0].relevanceBasis)
        self.assertTrue(response.results[0].caseStage)
        self.assertIn(response.results[0].caseStageConfidence, {"High", "Medium", "Low"})
        self.assertTrue(response.results[0].caseStageEvidence)
        self.assertTrue(response.results[0].outcomeRelief)
        self.assertTrue(response.results[0].authorityBasis)
        self.assertGreaterEqual(response.results[0].authorityScore, 0)
        self.assertTrue(response.results[0].sourceUrl)

    def test_year_filter_is_applied_to_both_retrieval_branches(self) -> None:
        year = "2024" if self.engine.corpus_version.startswith("import-") else "2022"
        response = self.engine.search(
            "Regular bail after long custody because the trial is delayed and liberty is affected.",
            SearchFilters(year=year),
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(all(result.year == year for result in response.results))

    def test_high_court_filter_excludes_supreme_court(self) -> None:
        if not any(case["court"] == "High Court" for case in self.engine._cases.values()):
            self.skipTest("The bundled fallback corpus contains Supreme Court decisions only")
        response = self.engine.search(
            "The accused seeks regular bail in an NDPS case after prolonged custody and trial delay.",
            SearchFilters(court="High Court"),
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(all(result.court != "Supreme Court" for result in response.results))

    def test_out_of_domain_query_returns_no_legal_results(self) -> None:
        response = self.engine.search(
            "Banana recipes and ocean weather forecasts for a weekend holiday.",
            SearchFilters(),
            5,
        )
        self.assertEqual(response.results, [])

    def test_default_filters_remain_optional(self) -> None:
        filters = SearchFilters()
        self.assertEqual(filters.court, "All Courts")
        self.assertEqual(filters.year, "All Years")
        response = self.engine.search(
            "An arbitral award is challenged for patent illegality under the Arbitration Act.",
            filters,
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(
            all("Active filter match" not in result.reasonCodes for result in response.results)
        )

    def test_lexical_candidates_are_unique_judgments(self) -> None:
        candidates = self.engine._lexical(
            "The legal heirs seek partition of inherited immovable property under Hindu succession law.",
            SearchFilters(),
            50,
        )
        case_ids = [self.engine._chunks[item.chunk_id]["case_id"] for item in candidates]
        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_semantic_index_has_two_context_vectors_per_judgment(self) -> None:
        self.assertEqual(len(self.engine._vector_case_ids), self.engine.case_count * 2)
        self.assertEqual(set(self.engine._vector_kinds), {"facts", "decision"})
        counts: dict[str, int] = {}
        for case_id in self.engine._vector_case_ids:
            counts[case_id] = counts.get(case_id, 0) + 1
        self.assertTrue(all(count == 2 for count in counts.values()))
        self.assertEqual(len(self.engine._context_anchor_cache), self.engine.case_count)

    def test_dense_candidates_are_unique_judgments(self) -> None:
        candidates = self.engine._dense(
            "Legal heirs seek partition of inherited immovable property.",
            SearchFilters(),
            50,
        )
        case_ids = [self.engine._chunks[item.chunk_id]["case_id"] for item in candidates]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertTrue(all(item.match_kind in {"facts", "decision"} for item in candidates))

    def test_succession_query_prioritizes_same_statute_and_domain(self) -> None:
        if not self.engine.corpus_version.startswith("import-"):
            self.skipTest("The small fallback corpus does not contain succession cases")
        response = self.engine.search(
            "Two brothers are equal legal heirs to immovable property left by their father "
            "under the Hindu Succession Act and seek one half share each.",
            SearchFilters(),
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(
            any("Hindu Succession Act, 1956" in reason for reason in response.results[0].reasonCodes)
        )
        self.assertNotIn("sunni law", response.results[0].matchedEvidence.lower())

    def test_substantive_issue_filter_uses_primary_case_context(self) -> None:
        if not self.engine.corpus_version.startswith("import-"):
            self.skipTest("The small fallback corpus does not contain succession cases")
        selected_issue = "Succession / Inheritance"
        response = self.engine.search(
            "Two brothers inherit their Hindu father's immovable property intestate under Section 8 "
            "of the Hindu Succession Act and seek equal shares.",
            SearchFilters(issue=selected_issue),
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(
            all(selected_issue in result.filterIssues for result in response.results)
        )
        self.assertIn(selected_issue, response.results[0].legalIssues)

    def test_requested_outcome_side_is_enforced(self) -> None:
        selected = "Petitioner / Appellant side succeeded"
        response = self.engine.search(
            "The accused seeks regular bail after prolonged custody because the trial remains delayed.",
            SearchFilters(outcome=selected),
            5,
        )
        self.assertTrue(response.results)
        self.assertTrue(
            all(
                self.engine._matches_outcome_filter(selected, result.winner, result.matterStatus)
                for result in response.results
            )
        )
        self.assertTrue(
            all(any("Requested outcome match" in reason for reason in result.reasonCodes) for result in response.results)
        )


if __name__ == "__main__":
    unittest.main()
