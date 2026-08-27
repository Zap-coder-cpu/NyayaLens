import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.case_analysis import (  # noqa: E402
    build_case_summary,
    extract_case_stage,
    extract_disposition,
    infer_bench_strength,
)


class CaseAnalysisTests(unittest.TestCase):
    def test_allowed_appeal_and_completed_trial_are_kept_separate(self) -> None:
        disposition = extract_disposition(
            "The trial court convicted the appellant after recording the evidence. "
            "For the reasons stated above, the appeal is allowed and the conviction is set aside."
        )
        self.assertEqual(disposition.matter_status, "Disposed")
        self.assertEqual(disposition.trial_status, "Trial completed")
        self.assertEqual(disposition.winner, "Appellant succeeded")

    def test_pending_trial_is_not_inferred_as_completed_from_disposal(self) -> None:
        disposition = extract_disposition(
            "The trial is pending and is unlikely to conclude soon. "
            "The applicant shall be released on regular bail. The application is disposed of."
        )
        self.assertEqual(disposition.trial_status, "Trial ongoing")
        self.assertEqual(disposition.winner, "Accused / applicant succeeded")

    def test_ambiguous_winner_requires_verification(self) -> None:
        disposition = extract_disposition("The parties made submissions. The matter is disposed of accordingly.")
        self.assertIn("verify", disposition.winner.lower())

    def test_summary_is_query_focused_and_bounded(self) -> None:
        summary = build_case_summary(
            "The prosecution cited several witnesses. The accused has remained in custody for two years. "
            "The charge sheet has been filed and investigation is complete. The evidence is documentary. "
            "The court discussed an unrelated procedural filing.",
            "Bail after prolonged custody because investigation is complete and evidence is documentary.",
        )
        self.assertIn("custody", summary.lower())
        self.assertIn("investigation", summary.lower())
        self.assertLessEqual(len(summary), 850)

    def test_case_stage_uses_complete_judgment_evidence(self) -> None:
        stage = extract_case_stage(
            "The FIR was registered and a charge sheet was filed. "
            "Only 4 prosecution witnesses have been examined and the trial is unlikely to conclude soon. "
            "The bail application is disposed of accordingly.",
            "Bail application under Section 439 CrPC",
            ["Regular Bail", "Criminal Law"],
        )
        self.assertEqual(stage.stage, "Trial ongoing")
        self.assertEqual(stage.confidence, "High")
        self.assertIn("trial", stage.evidence.lower())

    def test_non_criminal_case_marks_trial_stage_not_applicable(self) -> None:
        stage = extract_case_stage(
            "The arbitral award concerns performance of a commercial contract.",
            "Arbitration petition under Section 11",
            ["Arbitration"],
        )
        self.assertEqual(stage.stage, "Not applicable")

    def test_bench_strength_is_extracted_conservatively(self) -> None:
        bench = infer_bench_strength("This matter was referred to a five-judge bench for decision.")
        self.assertEqual(bench.size, 5)
        self.assertEqual(bench.label, "Five-judge bench")

        header_bench = infer_bench_strength("Author: A Judge\nBench: Abhay S. Oka, Ajay Rastogi\nJUDGMENT")
        self.assertEqual(header_bench.size, 2)
        self.assertEqual(header_bench.label, "Division bench")


if __name__ == "__main__":
    unittest.main()
