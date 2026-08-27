import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.ingestion import (  # noqa: E402
    MANIFEST_COLUMNS,
    ExtractedPdf,
    _controlling_metadata,
    classify_passage_role,
    classify_issues,
    parse_case_number,
    parse_citation,
    parse_court,
    parse_date,
    parse_source_url,
    parse_title,
)


def fixture(
    filename: str,
    text: str,
    metadata: dict[str, str] | None = None,
    source_group: str = "test",
) -> ExtractedPdf:
    return ExtractedPdf(
        path=Path(filename),
        relative_path=f"data/incoming/test/{filename}",
        source_group=source_group,
        text=text,
        metadata=metadata or {},
        pages=1,
        extraction_method="embedded",
        quality=0.9,
        sha256="a" * 64,
        warnings=[],
    )


class IngestionTests(unittest.TestCase):
    def test_manifest_schema_is_exact(self) -> None:
        self.assertEqual(
            MANIFEST_COLUMNS,
            ["id", "title", "court", "date", "citation", "case_number", "issues", "source_url", "pdf_filename"],
        )

    def test_high_court_filename_and_neutral_citation(self) -> None:
        document = fixture(
            "0003_UPHC016752372024_1_2025-01-15.pdf",
            "2025:AHC:6588\nRam Byas Singh\nApplicant\nVersus\nState of U.P.\nOpposite Party\nregular bail under Section 439",
        )
        self.assertEqual(parse_court(document), "Allahabad High Court")
        self.assertEqual(parse_date(document), "2025-01-15")
        self.assertEqual(parse_case_number(document), "UPHC016752372024")
        self.assertEqual(parse_citation(document), "2025:AHC:6588")
        self.assertIn("Regular Bail", classify_issues(document.text))

    def test_supreme_court_metadata_and_exact_source_url(self) -> None:
        document = fixture(
            "Asha_Devi_vs_State_Of_India_on_2_February_2024.pdf",
            "2024 INSC 123\nCIVIL APPEAL NO. 12 OF 2024\nIndian Kanoon - https://indiankanoon.org/doc/123456/",
            {"/Title": "Asha Devi vs State Of India on 2 February, 2024"},
            "supreme-court-2024",
        )
        self.assertEqual(parse_court(document), "Supreme Court")
        self.assertEqual(parse_date(document), "2024-02-02")
        self.assertEqual(parse_title(document), "Asha Devi vs State Of India")
        self.assertEqual(parse_citation(document), "2024 INSC 123")
        self.assertEqual(parse_source_url(document), "https://indiankanoon.org/doc/123456/")

    def test_supreme_court_ocr_header_and_reported_citation(self) -> None:
        document = fixture(
            "Abc_vs_State_on_6_July_2015_1.PDF",
            "Abc vs State on 6 July, 2015\n"
            "Equivalent citations: AIR 2015 SUPREME COURT 2569, (2015) 10 SCC 1\n"
            "IN THE SUPRME COURT OF INDIA\nCIVIL APPELLATE JURISDICTION",
            source_group="archive_2015_2022",
        )
        self.assertEqual(parse_court(document), "Supreme Court")
        self.assertEqual(parse_citation(document), "(2015) 10 SCC 1")

    def test_cited_authority_is_not_used_as_the_current_case_citation(self) -> None:
        document = fixture(
            "Union_Of_India_vs_Ganpati_Dealcom_on_23_August_2022_1.PDF",
            "Union of India vs Ganpati Dealcom on 23 August, 2022\n"
            "Author: N.V. Ramana\nIN THE SUPREME COURT OF INDIA\n"
            "The earlier decision reported in (2016) 3 SCC 183 was considered.",
            source_group="supreme-court-2015-2022",
        )
        self.assertEqual(parse_citation(document), "")

    def test_single_quoted_precedent_is_classified_as_cited_authority(self) -> None:
        passage = (
            "In State of Example v. Arun Kumar, (2020) 1 SCC 12, this Court "
            "observed as follows: the conditions in Section 37 of the NDPS Act "
            "must be applied strictly. The quoted extract is reproduced below."
        )
        self.assertEqual(classify_passage_role(passage, 4, 10), "Cited authorities")

    def test_present_court_holding_is_not_demoted_to_cited_authority(self) -> None:
        passage = (
            "We have considered A v. B, (2019) 1 SCC 1; C v. D, (2020) 2 SCC 2; "
            "and E v. F, (2021) 3 SCC 3. In the present case, the evidence does "
            "not satisfy the statutory test. We therefore hold that the appeal succeeds."
        )
        self.assertEqual(classify_passage_role(passage, 8, 10), "Court reasoning")

    def test_first_person_words_inside_authority_quote_remain_cited(self) -> None:
        passage = (
            "In State of Example v. Arun Kumar, AIR 2020 SC 123, this Court "
            "observed as follows: We hold that Section 37 applies to that earlier matter."
        )
        self.assertEqual(classify_passage_role(passage, 4, 10), "Cited authorities")

    def test_controlling_metadata_excludes_submissions_and_quoted_law(self) -> None:
        chunks = [
            {
                "section": "Cited authorities",
                "legalDomains": ["Bail / Criminal Procedure"],
                "statutes": ["NDPS Act"],
                "sections": ["37"],
                "provisionPairs": [{"statute": "NDPS Act", "section": "37"}],
                "postures": ["Bail application"],
                "reliefs": ["Bail"],
                "materialFacts": [{"name": "custody", "value": "prolonged"}],
            },
            {
                "section": "Party submissions",
                "legalDomains": ["Economic Offences"],
                "statutes": ["PMLA"],
                "sections": ["45"],
                "provisionPairs": [{"statute": "PMLA", "section": "45"}],
                "postures": [],
                "reliefs": ["Bail"],
                "materialFacts": [],
            },
            {
                "section": "Court reasoning",
                "legalDomains": ["Succession / Inheritance"],
                "statutes": ["Hindu Succession Act"],
                "sections": ["8"],
                "provisionPairs": [{"statute": "Hindu Succession Act", "section": "8"}],
                "postures": ["Civil appeal"],
                "reliefs": ["Partition"],
                "materialFacts": [{"name": "succession mode", "value": "intestate"}],
            },
        ]

        result = _controlling_metadata(chunks)

        self.assertEqual(result["controllingLegalDomains"], ["Succession / Inheritance"])
        self.assertEqual(result["controllingStatutes"], ["Hindu Succession Act"])
        self.assertEqual(result["controllingSections"], ["8"])
        self.assertEqual(
            result["controllingProvisionPairs"],
            [{"statute": "Hindu Succession Act", "section": "8"}],
        )
        self.assertEqual(result["controllingPostures"], ["Civil appeal"])
        self.assertEqual(result["controllingReliefs"], ["Partition"])
        self.assertEqual(
            result["controllingMaterialFacts"],
            [{"name": "succession mode", "value": "intestate"}],
        )

    def test_repeated_neutral_mentions_can_establish_controlling_metadata(self) -> None:
        chunks = [
            {"section": "Material facts"},
            {"section": "Party submissions"},
            {"section": "Judgment passage", "statutes": ["Arbitration Act"]},
            {"section": "Judgment passage", "statutes": ["Arbitration Act"]},
        ]
        result = _controlling_metadata(chunks)
        self.assertEqual(result["controllingStatutes"], ["Arbitration Act"])


if __name__ == "__main__":
    unittest.main()
