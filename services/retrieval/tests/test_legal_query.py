import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.legal_query import analyze_legal_query, profile_signals  # noqa: E402


class LegalQueryAnalysisTests(unittest.TestCase):
    def test_extracts_succession_statute_relationship_and_relief(self) -> None:
        profile = analyze_legal_query(
            "Two brothers are the legal heirs of their father and claim one half share each "
            "in his immovable property under the Hindu Succession Act, 1956."
        )
        self.assertIn("Succession / Inheritance", profile.domains)
        self.assertIn("Property / Land", profile.domains)
        self.assertIn("Hindu Succession Act, 1956", profile.statutes)
        self.assertIn("Partition / declaration of share", profile.reliefs)
        self.assertIn("Siblings / co-heirs", profile.relationships)

    def test_sections_remain_linkable_to_specific_statute(self) -> None:
        profile = analyze_legal_query(
            "Apply Section 8 of the Hindu Succession Act to intestate property."
        )
        self.assertEqual(profile.sections, ("Section 8",))
        self.assertEqual(profile.statutes, ("Hindu Succession Act, 1956",))
        self.assertIn("Intestate Succession", profile.concepts)

    def test_negation_is_not_treated_as_positive_risk(self) -> None:
        profile = analyze_legal_query(
            "There is no allegation that the applicant may abscond or influence witnesses."
        )
        facts = dict(profile.facts)
        self.assertEqual(facts["flight_risk"], "absent")
        self.assertEqual(facts["witness_interference"], "absent")
        self.assertNotIn("Flight Risk", profile.concepts)
        self.assertNotIn("Witness Interference", profile.concepts)
        signals = profile_signals(profile)
        self.assertIn("Flight Risk: absent", signals)
        self.assertIn("Witness Interference: absent", signals)

    def test_plain_negation_variants_remain_absent(self) -> None:
        profile = analyze_legal_query(
            "The accused is not likely to abscond and did not influence witnesses."
        )
        facts = dict(profile.facts)
        self.assertEqual(facts["flight_risk"], "absent")
        self.assertEqual(facts["witness_interference"], "absent")

    def test_invalid_will_is_not_treated_as_testamentary_succession(self) -> None:
        profile = analyze_legal_query(
            "The alleged will is invalid, so the estate must devolve without a valid will."
        )
        self.assertEqual(dict(profile.facts)["succession_mode"], "intestate")
        self.assertIn("Succession / Inheritance", profile.domains)

    def test_modal_will_does_not_invent_a_succession_dispute(self) -> None:
        profile = analyze_legal_query(
            "The criminal appeal will be heard tomorrow and the accused will remain on bail."
        )
        self.assertNotIn("Succession / Inheritance", profile.domains)

    def test_detects_material_fact_contradictions_as_distinct_values(self) -> None:
        complete = dict(
            analyze_legal_query("The investigation is complete and the charge sheet has been filed.").facts
        )
        pending = dict(
            analyze_legal_query("The investigation remains pending and no charge sheet was filed.").facts
        )
        self.assertEqual(complete["investigation_status"], "complete")
        self.assertEqual(pending["investigation_status"], "pending")

    def test_exposed_signals_are_transparent(self) -> None:
        signals = profile_signals(
            analyze_legal_query("Default bail is claimed under Section 167(2) of the CrPC.")
        )
        self.assertIn("Default Bail", signals)
        self.assertIn("Code of Criminal Procedure, 1973", signals)
        self.assertIn("Section 167(2)", signals)

    def test_pairs_section_with_act_and_extracts_context(self) -> None:
        profile = analyze_legal_query(
            "In a civil appeal, two brothers claim one half share under Section 8 "
            "of the Hindu Succession Act."
        )
        self.assertIn(
            ("Hindu Succession Act, 1956", "Section 8"), profile.provision_pairs
        )
        self.assertIn("Civil appeal", profile.postures)
        self.assertIn("two brothers", profile.material_phrases)
        self.assertIn("1/2 share", profile.quantities)

    def test_decimal_quantity_does_not_crash_or_get_treated_as_year(self) -> None:
        profile = analyze_legal_query(
            "The disputed amount was Rs. 4.11 crore under the agreement."
        )
        self.assertIn("4.11", profile.quantities)

    def test_tenancy_is_primary_without_inventing_a_spousal_dispute(self) -> None:
        profile = analyze_legal_query(
            "The landlord seeks eviction of the deceased tenant; the tenant's wife "
            "claims protection under the rent-control law."
        )
        self.assertIn("Tenancy / Rent Control", profile.domains)
        self.assertIn("Eviction / possession", profile.reliefs)
        self.assertNotIn("Spouses", profile.relationships)

    def test_tenants_in_common_is_concurrent_ownership_not_rent_control(self) -> None:
        profile = analyze_legal_query(
            "Under Section 19 of the Hindu Succession Act, the heirs take the property "
            "as tenants-in-common and not as joint tenants."
        )
        self.assertIn("Succession / Inheritance", profile.domains)
        self.assertNotIn("Tenancy / Rent Control", profile.domains)
        self.assertNotIn("Landlord Tenant", profile.concepts)

    def test_property_character_is_contextual_fact(self) -> None:
        self_acquired = dict(
            analyze_legal_query("The estate was the father's self-acquired property.").facts
        )
        ancestral = dict(
            analyze_legal_query("The dispute concerns ancestral coparcenary property.").facts
        )
        self.assertEqual(self_acquired["property_character"], "self_acquired")
        self.assertEqual(ancestral["property_character"], "ancestral_coparcenary")


if __name__ == "__main__":
    unittest.main()
