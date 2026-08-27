from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.engine import SemanticEngine  # noqa: E402
from app.legal_query import analyze_legal_query  # noqa: E402


def _synthetic_engine(case_specs: dict[str, list[tuple[str, str]]]) -> SemanticEngine:
    """Build only the in-memory state needed by deterministic reranking helpers."""

    engine = SemanticEngine.__new__(SemanticEngine)
    engine._cases = {}
    engine._chunks = {}
    engine._chunks_by_case = defaultdict(list)
    for case_id, chunks in case_specs.items():
        engine._cases[case_id] = {
            "id": case_id,
            "title": f"Synthetic {case_id}",
            "citation": "Citation not extracted - verify source document",
            "court": "Supreme Court",
            "legalDomains": [],
            "statutes": [],
            "sections": [],
            "provisionPairs": [],
            "reliefs": [],
        }
        for index, (section, evidence) in enumerate(chunks):
            chunk_id = f"{case_id}-chunk-{index}"
            engine._chunks[chunk_id] = {
                "id": chunk_id,
                "case_id": case_id,
                "section": section,
                "evidence": evidence,
            }
            engine._chunks_by_case[case_id].append(chunk_id)
    return engine


def _score(
    engine: SemanticEngine,
    case_id: str,
    query: str,
    *,
    chunk_index: int = 0,
) -> tuple[float, list[str], int, int]:
    chunk_id = engine._chunks_by_case[case_id][chunk_index]
    return engine._legal_relevance_adjustment(
        case_id,
        chunk_id,
        query,
        analyze_legal_query(query),
    )


class LegalQueryContextRegressionTests(unittest.TestCase):
    def test_negated_risks_are_not_flipped_by_positive_words_inside_them(self) -> None:
        variants = (
            "Neither the accused nor his family has threatened witnesses, and there is "
            "no possibility of absconding.",
            "The applicant has never intimidated a witness and cannot abscond.",
        )
        for text in variants:
            with self.subTest(text=text):
                facts = dict(analyze_legal_query(text).facts)
                self.assertEqual(facts.get("flight_risk"), "absent")
                self.assertEqual(facts.get("witness_interference"), "absent")

    def test_completed_investigation_tolerates_ordinary_legal_wording(self) -> None:
        variants = (
            "Investigation stands completed and the charge-sheet has already been filed.",
            "The investigating agency completed its investigation and filed the final report.",
        )
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(
                    dict(analyze_legal_query(text).facts).get("investigation_status"),
                    "complete",
                )

    def test_sibling_relationship_covers_gender_and_number_variants(self) -> None:
        for relationship in ("two sisters", "a brother and sister", "three siblings"):
            with self.subTest(relationship=relationship):
                profile = analyze_legal_query(
                    f"{relationship} seek partition as equal legal heirs of their father."
                )
                self.assertIn("Siblings / co-heirs", profile.relationships)

    def test_procedural_posture_covers_common_court_descriptions(self) -> None:
        examples = {
            "An appeal from the original decree in a partition suit is before the Court.": "Civil appeal",
            "SLP No. 123 of 2025 challenges refusal of leave.": "Special leave petition",
            "The accused filed a criminal revision petition against the conviction.": "Revision",
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertIn(expected, analyze_legal_query(text).postures)

    def test_multiple_acts_do_not_create_false_cross_provision_pairs(self) -> None:
        profile = analyze_legal_query(
            "Section 8 of the Hindu Succession Act governs the estate, while Section 34 "
            "of the Arbitration and Conciliation Act governs the award challenge."
        )
        expected = {
            ("Hindu Succession Act, 1956", "Section 8"),
            ("Arbitration and Conciliation Act, 1996", "Section 34"),
        }
        self.assertEqual(set(profile.provision_pairs), expected)

    def test_quantities_exclude_act_years_and_provision_numbers(self) -> None:
        profile = analyze_legal_query(
            "Under Section 8 of the Hindu Succession Act, 1956, each co-heir claims "
            "one-half share after two years."
        )
        self.assertIn("1/2 share", profile.quantities)
        self.assertIn("2 year", profile.quantities)
        self.assertNotIn("8", profile.quantities)
        self.assertNotIn("1956", profile.quantities)


class PassageRoleRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _synthetic_engine(
            {
                "roles": [
                    (
                        "party submissions",
                        "Learned counsel submitted that the arbitral award suffers from patent illegality.",
                    ),
                    (
                        "cited authorities",
                        "Alpha v. State (2019) 1 SCC 1; Beta versus Union (2020) 2 SCC 2; "
                        "Gamma v. Board AIR 2021 SC 3.",
                    ),
                    (
                        "material facts",
                        "The material facts show that the parties executed an arbitration agreement.",
                    ),
                    (
                        "court reasoning",
                        "We hold that the award discloses no patent illegality under the Arbitration Act.",
                    ),
                    (
                        "operative order",
                        "Accordingly, the appeal is dismissed and the award is affirmed.",
                    ),
                    (
                        "judgment passage",
                        "In Alpha v. State, (2019) 1 SCC 1, the earlier Court observed as "
                        "follows: we hold that the arbitral award suffers from patent illegality.",
                    ),
                ]
            }
        )
        self.profile = analyze_legal_query(
            "Set aside an arbitral award for patent illegality under the Arbitration Act."
        )

    def _role(self, index: int) -> tuple[float, str]:
        chunk_id = self.engine._chunks_by_case["roles"][index]
        return self.engine._passage_role_adjustment("roles", chunk_id, self.profile)

    def test_current_court_reasoning_outranks_party_submissions(self) -> None:
        submission_score, submission_reason = self._role(0)
        reasoning_score, reasoning_reason = self._role(3)
        self.assertGreater(reasoning_score, submission_score)
        self.assertIn("party submission", submission_reason.lower())
        self.assertIn("court's reasoning", reasoning_reason.lower())

    def test_material_facts_outrank_unadopted_cited_authorities(self) -> None:
        citation_score, citation_reason = self._role(1)
        facts_score, facts_reason = self._role(2)
        self.assertGreater(facts_score, citation_score)
        self.assertIn("cited authorities", citation_reason.lower())
        self.assertIn("material facts", facts_reason.lower())

    def test_operative_order_is_positive_when_query_requests_relief(self) -> None:
        order_score, order_reason = self._role(4)
        self.assertGreater(order_score, 0)
        self.assertIn("operative order", order_reason.lower())

    def test_first_person_holding_inside_precedent_quote_is_not_current_reasoning(self) -> None:
        citation_score, citation_reason = self._role(5)
        reasoning_score, _ = self._role(3)
        self.assertLess(citation_score, reasoning_score)
        self.assertIn("cited authorities", citation_reason.lower())


class LegalRerankingRegressionTests(unittest.TestCase):
    def test_same_personal_law_and_succession_facts_beat_conflicting_regime(self) -> None:
        engine = _synthetic_engine(
            {
                "hindu": [
                    (
                        "material facts",
                        "In this civil appeal from a partition suit, two brothers are co-heirs. "
                        "Their Hindu father died intestate without a will. Each claims one-half "
                        "share in the immovable property under Section 8 of the Hindu Succession Act.",
                    )
                ],
                "muslim": [
                    (
                        "material facts",
                        "In this civil appeal from a partition suit, two brothers are co-heirs. "
                        "Their father died intestate and the estate devolves under Sunni law. "
                        "Each claims one-half share in the immovable property.",
                    )
                ],
            }
        )
        query = (
            "In a civil appeal, two brothers seek one-half share each in their Hindu father's "
            "immovable property under Section 8 of the Hindu Succession Act because he died intestate."
        )
        hindu_score, hindu_reasons, _, hindu_contradictions = _score(engine, "hindu", query)
        muslim_score, muslim_reasons, _, muslim_contradictions = _score(engine, "muslim", query)

        self.assertGreater(hindu_score, muslim_score)
        self.assertEqual(hindu_contradictions, 0)
        self.assertGreater(muslim_contradictions, hindu_contradictions)
        self.assertTrue(any("Same Act\u2013provision pair" in reason for reason in hindu_reasons))
        self.assertTrue(any("Contradictory fact" in reason for reason in muslim_reasons))

    def test_matching_bail_facts_beat_opposite_risk_and_investigation_facts(self) -> None:
        engine = _synthetic_engine(
            {
                "matched": [
                    (
                        "material facts",
                        "This bail application seeks regular bail after prolonged custody. "
                        "The investigation is complete and the charge sheet has been filed. "
                        "There is no flight risk and no witness interference.",
                    )
                ],
                "contradicted": [
                    (
                        "material facts",
                        "This bail application seeks regular bail after prolonged custody. "
                        "The investigation is pending, no charge sheet has been filed, the accused "
                        "is likely to abscond, and he threatened witnesses.",
                    )
                ],
            }
        )
        query = (
            "The accused seeks regular bail after prolonged custody. The investigation is complete, "
            "there is no flight risk, and there is no witness interference."
        )
        matched_score, matched_reasons, _, matched_contradictions = _score(engine, "matched", query)
        contradicted_score, contradicted_reasons, _, contradicted_contradictions = _score(
            engine, "contradicted", query
        )

        self.assertGreater(matched_score, contradicted_score)
        self.assertEqual(matched_contradictions, 0)
        self.assertGreaterEqual(contradicted_contradictions, 3)
        self.assertTrue(any("Matching fact" in reason for reason in matched_reasons))
        self.assertTrue(any("Contradictory fact" in reason for reason in contradicted_reasons))

    def test_exact_act_section_pair_beats_same_number_under_another_act(self) -> None:
        engine = _synthetic_engine(
            {
                "arbitration": [
                    (
                        "court reasoning",
                        "In this challenge to the arbitral award, the Court applies Section 34 "
                        "of the Arbitration and Conciliation Act to the plea of patent illegality.",
                    )
                ],
                "tax": [
                    (
                        "court reasoning",
                        "This income-tax appeal concerns reassessment under Section 34 of the "
                        "Income-tax Act and contains no arbitral award challenge.",
                    )
                ],
            }
        )
        query = (
            "Set aside an arbitral award for patent illegality under Section 34 of the "
            "Arbitration and Conciliation Act."
        )
        arbitration_score, arbitration_reasons, _, arbitration_contradictions = _score(
            engine, "arbitration", query
        )
        tax_score, tax_reasons, _, tax_contradictions = _score(engine, "tax", query)

        self.assertGreater(arbitration_score, tax_score)
        self.assertEqual(arbitration_contradictions, 0)
        self.assertGreater(tax_contradictions, arbitration_contradictions)
        self.assertTrue(any("Same Act\u2013provision pair" in reason for reason in arbitration_reasons))
        self.assertTrue(any("different statute" in reason.lower() for reason in tax_reasons))

    def test_matching_procedural_posture_receives_a_relative_boost(self) -> None:
        engine = _synthetic_engine(
            {
                "appeal": [
                    (
                        "material facts",
                        "This civil appeal concerns two brothers seeking partition of inherited "
                        "immovable property as equal co-heirs.",
                    )
                ],
                "original": [
                    (
                        "material facts",
                        "This original civil suit concerns two brothers seeking partition of inherited "
                        "immovable property as equal co-heirs.",
                    )
                ],
            }
        )
        query = (
            "In a civil appeal, two brothers seek partition of inherited immovable property "
            "as equal co-heirs."
        )
        appeal_score, appeal_reasons, _, _ = _score(engine, "appeal", query)
        original_score, original_reasons, _, _ = _score(engine, "original", query)

        self.assertGreater(appeal_score, original_score)
        self.assertTrue(any("Same procedural posture" in reason for reason in appeal_reasons))
        self.assertFalse(any("Same procedural posture" in reason for reason in original_reasons))


if __name__ == "__main__":
    unittest.main()
