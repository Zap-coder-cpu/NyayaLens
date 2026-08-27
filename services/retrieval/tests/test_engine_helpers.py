import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.engine import RRF_K, SemanticEngine, extract_signals, is_legal_query, lexical_tokens  # noqa: E402
from app.models import SearchFilters, SearchRequest  # noqa: E402


class EngineHelperTests(unittest.TestCase):
    def test_extracts_legal_synonyms_and_sections(self) -> None:
        signals = extract_signals(
            "Pre-arrest bail is requested under Section 438 because there is no risk the applicant will abscond."
        )
        self.assertIn("Anticipatory Bail", signals)
        self.assertIn("Flight Risk", signals)
        self.assertIn("Section 438", signals)

    def test_lexical_tokens_remove_common_words(self) -> None:
        self.assertEqual(lexical_tokens("The applicant seeks bail under Section 439"), ["bail", "under", "section", "439"])

    def test_request_rejects_short_query(self) -> None:
        with self.assertRaises(ValueError):
            SearchRequest(query="regular bail", filters=SearchFilters())

    def test_rrf_constant_is_documented_default(self) -> None:
        self.assertEqual(RRF_K, 60)

    def test_outcome_filter_validation_and_side_mapping(self) -> None:
        filters = SearchFilters(outcome="Petitioner / Appellant side succeeded")
        self.assertEqual(filters.outcome, "Petitioner / Appellant side succeeded")
        with self.assertRaises(ValueError):
            SearchFilters(outcome="Petitioner definitely wins")

    def test_legal_domain_gate(self) -> None:
        self.assertTrue(is_legal_query("Can an accused receive bail under Section 439?"))
        self.assertFalse(is_legal_query("Banana recipes and ocean weather forecasts"))

    def test_lexical_row_does_not_repeat_noisy_whole_judgment_issues(self) -> None:
        text = SemanticEngine._chunk_index_text(
            {
                "title": "A v B",
                "citation": "2025 INSC 1",
                "legalIssues": ["Taxation", "Criminal Law", "Constitutional Law"],
            },
            {
                "evidence": "The two legal heirs seek partition of immovable property.",
                "legalDomains": ["Succession / Inheritance"],
                "statutes": [],
                "sections": [],
                "reliefs": ["Partition / declaration of share"],
                "postures": [],
            },
        ).lower()
        self.assertIn("succession", text)
        self.assertNotIn("taxation", text)
        self.assertNotIn("criminal law", text)


if __name__ == "__main__":
    unittest.main()
