from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .case_analysis import extract_case_stage, extract_disposition, infer_bench_strength
from .legal_query import analyze_legal_query

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INCOMING_ROOT = PROJECT_ROOT / "data" / "incoming"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
IMPORT_ROOT = Path(__file__).resolve().parents[1] / "data" / "import"
TEXT_CACHE_ROOT = PROCESSED_ROOT / "text-cache"
MANIFEST_PATH = PROCESSED_ROOT / "judgments.csv"
QA_PATH = PROCESSED_ROOT / "ingestion_qa.csv"
CORPUS_PATH = IMPORT_ROOT / "cases.json"

MANIFEST_COLUMNS = [
    "id",
    "title",
    "court",
    "date",
    "citation",
    "case_number",
    "issues",
    "source_url",
    "pdf_filename",
]

COURT_CODES = {
    "APHC": "Andhra Pradesh High Court",
    "BRHC": "Patna High Court",
    "CGHC": "Chhattisgarh High Court",
    "DLHC": "Delhi High Court",
    "GAHC": "Gauhati High Court",
    "GJHC": "Gujarat High Court",
    "HCBM": "Bombay High Court",
    "HBHC": "Telangana High Court",
    "HCMA": "Madras High Court",
    "HCMD": "Madras High Court - Madurai Bench",
    "HPHC": "Himachal Pradesh High Court",
    "JHHC": "Jharkhand High Court",
    "JKHC": "Jammu & Kashmir and Ladakh High Court",
    "KAHC": "Karnataka High Court",
    "ODHC": "Orissa High Court",
    "PHHC": "Punjab and Haryana High Court",
    "RJHC": "Rajasthan High Court",
    "UKHC": "Uttarakhand High Court",
    "UPHC": "Allahabad High Court",
    "WBCH": "Calcutta High Court",
}

ISSUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "Anticipatory Bail": (r"anticipatory bail", r"section\s+438", r"pre[- ]arrest bail"),
    "Default Bail": (r"default bail", r"statutory bail", r"section\s+167\s*\(\s*2\s*\)"),
    "Regular Bail": (r"regular bail", r"application.{0,30}\bbail\b", r"section\s+439", r"release.{0,20}\bon bail\b"),
    "Prolonged Custody": (r"prolonged custody", r"long incarceration", r"trial.{0,35}(?:delay|not likely to conclude)"),
    "Quashing of Criminal Proceedings": (r"quash(?:ing|ed)?.{0,30}(?:fir|criminal|proceedings)", r"section\s+(?:482|528).{0,20}(?:crpc|bnss|code)"),
    "Narcotics / NDPS": (r"\bndps\b", r"narcotic drugs", r"narcotics control bureau", r"commercial quantity"),
    "Economic Offences / PMLA": (r"\bpmla\b", r"money laundering", r"enforcement directorate", r"economic offence", r"prevention of corruption"),
    "Criminal Law": (r"\bfir\b", r"\bipc\b", r"\bbns\b", r"criminal appeal", r"criminal petition", r"criminal revision"),
    "Constitutional Law": (r"constitution of india", r"fundamental right", r"article\s+(?:14|19|21|32|226)\b", r"writ petition"),
    "Service Law": (r"service law", r"service matter", r"seniority", r"promotion", r"disciplinary proceedings", r"termination from service"),
    "Taxation": (r"income tax", r"goods and services tax", r"\bgst\b", r"central excise", r"customs act", r"tax appeal"),
    "Arbitration": (r"arbitration", r"arbitral tribunal", r"arbitral award"),
    "Property / Land": (r"land acquisition", r"transfer of property", r"property dispute", r"specific performance", r"immovable property"),
    "Succession / Inheritance": (
        r"hindu succession act", r"intestate succession", r"legal heirs?", r"class[ -]?i heirs?",
        r"coparcen(?:er|ary)", r"ancestral property", r"devol(?:ve|ution).{0,40}(?:heir|succession)",
    ),
    "Probate / Wills": (r"probate", r"letters of administration", r"testamentary", r"validity of.{0,20}will", r"executed.{0,20}will"),
    "Tenancy / Rent Control": (r"rent control", r"landlord.{0,30}tenant", r"eviction petition", r"tenancy"),
    "Family / Matrimonial": (r"matrimonial", r"hindu marriage act", r"domestic violence", r"divorce", r"maintenance"),
    "Motor Vehicles / Compensation": (r"motor vehicles act", r"motor accident", r"motor accident claims tribunal", r"insurance company.{0,80}compensation"),
    "Consumer Law": (r"consumer protection", r"consumer dispute", r"deficiency in service"),
    "Insolvency": (r"insolvency", r"bankruptcy code", r"\bibc\b", r"corporate debtor"),
    "Environmental Law": (r"environment protection", r"wildlife protection", r"forest conservation", r"pollution control", r"national green tribunal"),
    "Cheque Dishonour": (r"section\s+138", r"negotiable instruments act", r"dishonou?r of cheque"),
    "Civil Procedure": (r"civil procedure code", r"\bcpc\b", r"civil appeal", r"civil revision", r"second appeal"),
}

CASE_NUMBER_PATTERN = re.compile(
    r"(?im)^\s*((?:SLP|SPECIAL\s+LEAVE\s+PETITION|CIVIL\s+APPEAL|CRIMINAL\s+APPEAL|"
    r"WRIT\s+PETITION|REVIEW\s+PETITION|TRANSFER\s+PETITION|CURATIVE\s+PETITION|"
    r"CONTEMPT\s+PETITION|CRIMINAL\s+MISC(?:ELLANEOUS)?(?:\s+ANTICIPATORY\s+BAIL)?\s+APPLICATION|"
    r"CRL\.?\s*O\.?P\.?|CRL\.?\s*M\.?P\.?|CRM-M|MCRC|"
    r"W\.?P\.?(?:\s*\([A-Z/]+\))?|C\.?R\.?P\.?|ARB\.?P\.?|"
    r"[A-Z][A-Z()./-]{1,14}\s+(?:PETITION|APPLICATION|APPEAL|REVISION))"
    r"[^\n]{0,30}?(?:\bNO(?:S|\(S\))?\.?|:)\s+[A-Z0-9()./-]+(?:\s+OF\s+\d{4})?(?:\s*\(O&M\))?)"
)
NEUTRAL_CITATION_PATTERNS = (
    re.compile(r"\b(20\d{2}\s+INSC\s+\d+)\b", re.I),
    re.compile(r"\b(20\d{2}\s*:\s*[A-Z][A-Z-]{1,12}\s*:\s*\d+)\b", re.I),
    re.compile(r"\[(20\d{2}\s*:\s*[A-Z][A-Z-]{1,12}\s*:\s*\d+)\]", re.I),
)
REPORTED_CITATION_PATTERNS = (
    re.compile(r"(\(20\d{2}\)\s+\d+\s+SCC\s+\d+)\b", re.I),
    re.compile(r"\b(20\d{2}\s+SCC\s+ON(?:LINE|L)\s+SC\s+\d+)\b", re.I),
    re.compile(r"\b(AIR\s+20\d{2}\s+(?:SC|SUPREME\s+COURT)\s+\d+)\b", re.I),
)


@dataclass
class ExtractedPdf:
    path: Path
    relative_path: str
    source_group: str
    text: str
    metadata: dict[str, str]
    pages: int
    extraction_method: str
    quality: float
    sha256: str
    warnings: list[str]


def normalize_whitespace(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\ufeff", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def text_quality(text: str) -> float:
    if not text:
        return 0.0
    sample = text[:100_000]
    visible = [char for char in sample if not char.isspace()]
    if not visible:
        return 0.0
    letters = sum(char.isalpha() for char in visible)
    controls = sum(ord(char) < 32 and char not in "\n\t\r" for char in sample)
    replacement = sample.count("\ufffd") + sample.count("(cid:")
    words = re.findall(r"[A-Za-z]{3,}", sample)
    score = (letters / len(visible)) * min(1.0, len(words) / 120)
    score -= min(0.8, controls / max(1, len(sample)) * 30)
    score -= min(0.8, replacement / max(1, len(sample)) * 15)
    return max(0.0, min(1.0, score))


def _read_pdf(path: Path) -> ExtractedPdf:
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    source_group = path.relative_to(INCOMING_ROOT).parts[0]
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    cache_path = TEXT_CACHE_ROOT / f"{sha256}.json.gz"
    if cache_path.exists():
        with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
            cached = json.load(stream)
        return ExtractedPdf(
            path=path,
            relative_path=relative_path,
            source_group=source_group,
            text=cached["text"],
            metadata=cached["metadata"],
            pages=cached["pages"],
            extraction_method=cached["extraction_method"],
            quality=cached["quality"],
            sha256=sha256,
            warnings=cached["warnings"],
        )
    warnings: list[str] = []
    try:
        reader = PdfReader(path, strict=False)
        pages = len(reader.pages)
        page_texts: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_texts.append(f"\n\n[[PAGE {page_number}]]\n" + (page.extract_text() or ""))
            except Exception as error:  # malformed pages should not abort the batch
                warnings.append(f"page_{page_number}_extract_error:{type(error).__name__}")
        metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
        text = normalize_whitespace("".join(page_texts))
    except Exception as error:
        return ExtractedPdf(
            path=path,
            relative_path=relative_path,
            source_group=source_group,
            text="",
            metadata={},
            pages=0,
            extraction_method="failed",
            quality=0.0,
            sha256=sha256,
            warnings=[f"pdf_read_error:{type(error).__name__}"],
        )

    quality = text_quality(text)
    if len(text) < 500:
        warnings.append("insufficient_extracted_text")
    if quality < 0.42:
        warnings.append("low_text_quality")
    return ExtractedPdf(
        path=path,
        relative_path=relative_path,
        source_group=source_group,
        text=text,
        metadata=metadata,
        pages=pages,
        extraction_method="embedded_text",
        quality=quality,
        sha256=sha256,
        warnings=warnings,
    )


def discover_pdfs() -> list[Path]:
    return sorted(path for path in INCOMING_ROOT.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")


def extract_embedded_text(paths: Iterable[Path], workers: int = 6) -> list[ExtractedPdf]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_read_pdf, paths))


def apply_ocr(documents: list[ExtractedPdf]) -> int:
    candidates = [
        doc
        for doc in documents
        if (doc.quality < 0.42 or len(doc.text) < 500)
        and "ocr_did_not_improve_text" not in doc.warnings
    ]
    if not candidates:
        return 0

    import fitz
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    for position, document in enumerate(candidates, start=1):
        page_texts: list[str] = []
        try:
            with fitz.open(document.path) as pdf:
                document.pages = len(pdf)
                for page_number, page in enumerate(pdf, start=1):
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                        pixmap.height, pixmap.width, pixmap.n
                    )
                    result, _ = engine(image)
                    lines = [item[1] for item in result] if result else []
                    page_texts.append(f"\n\n[[PAGE {page_number}]]\n" + "\n".join(lines))
            ocr_text = normalize_whitespace("".join(page_texts))
            ocr_quality = text_quality(ocr_text)
            if ocr_quality > document.quality and len(ocr_text) >= 500:
                document.text = ocr_text
                document.quality = ocr_quality
                document.extraction_method = "ocr"
                document.warnings = [warning for warning in document.warnings if warning not in {"low_text_quality", "insufficient_extracted_text"}]
            else:
                document.warnings.append("ocr_did_not_improve_text")
        except Exception as error:
            document.warnings.append(f"ocr_error:{type(error).__name__}")
        print(f"OCR {position}/{len(candidates)}: {document.path.name}", flush=True)
    return len(candidates)


def save_text_cache(documents: list[ExtractedPdf]) -> None:
    TEXT_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    for document in documents:
        cache_path = TEXT_CACHE_ROOT / f"{document.sha256}.json.gz"
        payload = {
            "text": document.text,
            "metadata": document.metadata,
            "pages": document.pages,
            "extraction_method": document.extraction_method,
            "quality": document.quality,
            "warnings": document.warnings,
        }
        with gzip.open(cache_path, "wt", encoding="utf-8", compresslevel=5) as stream:
            json.dump(payload, stream, ensure_ascii=False)


def parse_date(document: ExtractedPdf) -> str:
    filename = document.path.stem
    iso = re.search(r"_(20\d{2}-\d{2}-\d{2})$", filename)
    if iso:
        return iso.group(1)
    named = re.search(r"_on_(\d{1,2})_([A-Za-z]+)_(20\d{2})(?:_\d+)?$", filename, re.I)
    if named:
        try:
            return datetime.strptime(" ".join(named.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            pass
    text_date = re.search(r"(?i)(?:date(?:d|\s+of\s+decision)?\s*[:.-]?\s*)(\d{1,2}[./-]\d{1,2}[./-]20\d{2})", document.text[:12_000])
    if text_date:
        for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text_date.group(1), pattern).date().isoformat()
            except ValueError:
                continue
    return ""


def parse_court(document: ExtractedPdf) -> str:
    if document.source_group.startswith("supreme-court"):
        return "Supreme Court"
    head = document.text[:12_000]
    if re.search(r"(?i)\bIN\s+THE\s+SUPR[A-Z]*\s+COURT\s+OF\s+INDIA\b", head):
        return "Supreme Court"
    if re.search(r"(?im)^\s*Equivalent\s+citations?\s*:.*\b(?:SUPREME\s+COURT|SCC)\b", head):
        return "Supreme Court"
    match = re.match(r"\d+_([A-Z]{4})", document.path.name)
    return COURT_CODES.get(match.group(1), "High Court") if match else "High Court"


def clean_title(value: str) -> str:
    value = re.sub(r"(?i)\s+on\s+\d{1,2}\s+[A-Za-z]+,?\s+20\d{2}\s*$", "", value)
    value = re.sub(r"(?i)\s+(?:\.{2,}|…+)?\s*(petitioner|appellant|applicant|respondent)s?\s*$", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .:-")
    return value


def clean_party_line(value: str) -> str:
    value = re.sub(r"^\s*\d+\s*[-.)\]]\s*", "", value)
    value = re.split(r"(?i)\b(?:S/O|W/O|D/O|AGED\s+ABOUT|R/O|RESIDENT\s+OF|OCC\s*[:;])\b", value, maxsplit=1)[0]
    value = re.split(r"(?i)\s*(?:\.{2,}|…+)\s*(?:petitioner|appellant|applicant|respondent|opposite\s+part|opp\.?\s*part)", value, maxsplit=1)[0]
    value = re.split(r"(?i),?\s*rep(?:resented)?\s+by\b", value, maxsplit=1)[0]
    value = re.sub(
        r"(?i)\s*(?:\.{2,}|…+)?\s*(?:petitioner|appellant|applicant|respondent|opposite\s+part)(?:/s|\(s\)|s|ies)?\s*$",
        "",
        value,
    )
    return clean_title(value).strip(" ,.…")


def party_from_block(block: str, use_anchor: bool = True) -> str:
    lines = [line.strip(" .:-\t") for line in block.splitlines()]
    anchor = -1
    if use_anchor:
        for index, line in enumerate(lines):
            if re.search(
                r"(?i)(?:\bbetwee\w*\b|^case\s*(?:no|:)|^.*\b(?:petition|appeal|application|revision|mcrc|crm|crl|w\.p\.).*\d{3,}|^={3,}$)",
                line,
            ):
                anchor = index
    ignored = re.compile(
        r"(?i)^(?:and|with|\[\[page\s+\d+\]\]|in the high court.*|high court.*|court no.*|neutral citation.*|reserved|reportable|nafr|coram.*|present.*|appearance.*|order|judg(?:e?ment)|date.*|page no.*|case no.*|legal)$"
    )
    for line in lines[anchor + 1 :]:
        if not line or ignored.match(line) or re.fullmatch(r"[=_*#-]+", line):
            continue
        compact = re.sub(r"[^a-z]", "", line.lower())
        if compact.startswith("inthehighcourt") or compact.startswith("highcourtfor"):
            continue
        if any(
            marker in compact
            for marker in (
                "haryanaatchandigarh",
                "judicatureat",
                "orissaatcuttack",
                "jharkhandatranchi",
                "atnainital",
                "atbilaspur",
                "atamaravati",
                "atcalcutta",
                "atnewdelhi",
                "atpatna",
            )
        ):
            continue
        if re.match(r"(?i)^nos?\.?\s*[\d,./ -]+$", line):
            continue
        if re.search(r"(?i)neutral citation|\b20\d{2}\s*:[A-Z-]+:\d+|^page\s+\d+\s+of\s+\d+$", line):
            continue
        if re.match(r"(?i)^(?:CRM|CRL|MCRC|W\.?P\.?|C\.?R\.?P\.?|ARB\.?P\.?).*\d{3,}", line):
            continue
        if re.search(r"(?i)\bNO(?:S)?\.?\s*[:.-]?\s*\d{2,}", line):
            continue
        if not re.search(r"[A-Za-z]{2,}", line):
            continue
        party = clean_party_line(line)
        if len(party) >= 3 and not ignored.match(party):
            return party
    return ""


def parse_title(document: ExtractedPdf) -> str:
    metadata_title = clean_title(document.metadata.get("/Title", ""))
    if document.source_group.startswith("supreme-court") and len(metadata_title) > 8:
        return metadata_title

    head = document.text[:18_000]
    parenthetical = re.search(
        r"(?is)(?:\(\s*([^\]()]{3,300}?)\s+vs\.?\s+([^\]()]{3,300}?)\s*\)|"
        r"\[\s*([^\[\]]{3,300}?)\s+-vs-\s+([^\[\]]{3,300}?)\s*\])",
        head[:6_000],
    )
    if parenthetical:
        left = clean_party_line(parenthetical.group(1) or parenthetical.group(3))
        right = clean_party_line(parenthetical.group(2) or parenthetical.group(4))
        if left and right:
            return f"{left} v. {right}"

    labelled_pairs = (
        re.compile(r"(?im)^\s*Applicant\s*[:-]\s*(.+?)\s*$.*?^\s*Opposite\s+Party\s*[:-]\s*(.+?)\s*$", re.S),
        re.compile(r"(?im)^\s*Petitioner(?:/s|\(s\)|s)?\s*[:-]\s*(.+?)\s*$.*?^\s*Respondent(?:/s|\(s\)|s)?\s*[:-]\s*(.+?)\s*$", re.S),
    )
    for pattern in labelled_pairs:
        labelled = pattern.search(head)
        if labelled:
            left = clean_title(labelled.group(1).splitlines()[0])
            right = clean_title(labelled.group(2).splitlines()[0])
            if left and right:
                return f"{left} v. {right}"

    versus_line = re.search(
        r"(?im)^\s*-?\s*(?:VERSUS|V\s+E\s+R\s+S\s+U\s+S|VS\.?|V\.)\s*-?\s*$",
        head,
    )
    if versus_line:
        left = party_from_block(head[max(0, versus_line.start() - 8_000) : versus_line.start()])
        right = party_from_block(head[versus_line.end() : versus_line.end() + 4_000], use_anchor=False)
        if left and right:
            return f"{left[:220]} v. {right[:220]}"

    between = re.search(
        r"(?is)\bBetween\s*:\s*(.+?)\s*(?:\.{2,}|…+)?\s*PETITIONER[^\n]*\s*\n\s*AND\s*\n\s*(.+?)\s*(?:\.{2,}|…+)?\s*RESPONDENT[^\n]*",
        head,
    )
    if between:
        left = party_from_block("Between:\n" + between.group(1))
        right = party_from_block(between.group(2), use_anchor=False)
        if left and right:
            return f"{left[:220]} v. {right[:220]}"

    generic_between = re.search(
        r"(?is)\bBetwee\w*\s*:[ \t]*(.+?)\n[ \t]*AND[ \t]*\n(?:[^\n]*(?:PET|APPL)[^\n]*\n)?(.{3,4000})",
        head,
    )
    if generic_between:
        left = party_from_block("Between:\n" + generic_between.group(1))
        right = party_from_block(generic_between.group(2), use_anchor=False)
        if left and right:
            return f"{left[:220]} v. {right[:220]}"

    versus_pattern = re.compile(
        r"(?im)^\s*([^\n]{3,220}?)\s*(?:\.{2,}|…+)?\s*(?:petitioner|appellant|applicant)(?:/s|\(s\)|s)?\s*$"
        r"\s*\n\s*-?\s*(?:VERSUS|VS\.?|V\.)\s*-?\s*\n\s*([^\n]{3,220}?)(?:\s*(?:\.{2,}|…+)?\s*(?:respondent|opp\.?\s*part)(?:/s|\(s\)|s|ies)?)?\s*$"
    )
    candidates = list(versus_pattern.finditer(head))
    if candidates:
        first = candidates[0]
        left = clean_title(first.group(1))
        right = clean_title(first.group(2))
        if left and right:
            return f"{left} v. {right}"

    loose = re.search(r"(?is)\n\s*([^\n]{3,160})\s*\n\s*-?\s*(?:versus|vs\.?|v\.)\s*-?\s*\n\s*([^\n]{3,160})", head)
    if loose:
        left, right = clean_title(loose.group(1)), clean_title(loose.group(2))
        if left and right:
            return f"{left} v. {right}"

    in_re = re.search(r"(?im)^\s*In\s+Re\s*:\s*([^\n]{3,180})", head)
    if in_re:
        subject = clean_party_line(in_re.group(1))
        if subject:
            return f"In Re: {subject}"

    in_matter = re.search(r"(?im)^\s*In\s+the\s+matter\s+of\s*:\s*([^\n]{3,180})", head)
    if in_matter:
        subject = clean_party_line(in_matter.group(1))
        if subject:
            return f"In the matter of {subject}"

    if metadata_title and not re.search(r"(?i)^(microsoft word|document|\d+)$", metadata_title):
        return metadata_title
    docket_line = re.search(
        r"(?im)^\s*((?:Suo\s+Motu\s+)?(?:TR|W\.?P\.?(?:\(MD\))?|C\.?M\.?P\.?|MCRC|CRM|CRL)[^\n]{0,50}\b20\d{2})\s*$",
        head[:4_000],
    )
    if docket_line:
        return clean_title(docket_line.group(1))
    docket = parse_case_number(document)
    if docket:
        return docket
    cnr = parse_cnr(document.path.name)
    return f"CNR {cnr}" if cnr else document.path.stem


def parse_cnr(filename: str) -> str:
    match = re.match(r"\d+_([A-Z]{4,6}\d{10,20})", filename)
    return match.group(1) if match else ""


def parse_case_number(document: ExtractedPdf) -> str:
    match = CASE_NUMBER_PATTERN.search(document.text[:30_000])
    if match:
        candidate = normalize_whitespace(match.group(1)).replace("\n", " ")[:180]
        if re.search(r"\d", candidate) and not candidate.rstrip().endswith("-"):
            return candidate
    return parse_cnr(document.path.name)


def parse_citation(document: ExtractedPdf) -> str:
    head = document.text[:20_000]
    for pattern in NEUTRAL_CITATION_PATTERNS:
        match = pattern.search(head)
        if match:
            return re.sub(r"\s*:\s*", ":", re.sub(r"\s+", " ", match.group(1))).upper()
    equivalent = re.search(
        r"(?is)\bEquivalent\s+citations?\s*:\s*(.{1,3000}?)"
        r"(?=\n\s*(?:Author|Bench)\s*:|\n\s*(?:REPORTABLE|NON[- ]REPORTABLE)|\[\[PAGE|\Z)",
        head,
    )
    if not equivalent:
        return ""
    reported_citations = equivalent.group(1)
    for pattern in REPORTED_CITATION_PATTERNS:
        match = pattern.search(reported_citations)
        if match:
            citation = re.sub(r"\s+", " ", match.group(1)).upper()
            return re.sub(r"SUPREME\s+COURT", "SC", citation)
    return ""


def parse_source_url(document: ExtractedPdf) -> str:
    match = re.search(r"https?://(?:www\.)?indiankanoon\.org/doc/(\d+)/?", document.text, re.I)
    if match:
        return f"https://indiankanoon.org/doc/{match.group(1)}/"
    official = re.search(r"https?://[^\s<>()]+\.(?:gov|nic)\.in(?:/[^\s<>()]*)?", document.text, re.I)
    return official.group(0).rstrip(".,;')\"]") if official else ""


def classify_issues(text: str) -> list[str]:
    lowered = (text[:50_000] + "\n" + text[-20_000:]).lower()
    scored: list[tuple[int, str]] = []
    for issue, patterns in ISSUE_PATTERNS.items():
        score = sum(min(5, len(re.findall(pattern, lowered, re.I | re.S))) for pattern in patterns)
        if score:
            scored.append((score, issue))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [issue for _, issue in scored[:8]] or ["Unclassified"]


def stable_id(document: ExtractedPdf, court: str, citation: str, case_number: str) -> str:
    court_slug = "sc" if court == "Supreme Court" else "hc"
    source = parse_source_url(document)
    source_id = re.search(r"/doc/(\d+)/", source)
    if source_id:
        return f"{court_slug}-ik-{source_id.group(1)}"
    cnr = parse_cnr(document.path.name)
    if cnr:
        return f"{court_slug}-{cnr.lower()}"
    identity = "|".join((court, citation, case_number, document.sha256))
    return f"{court_slug}-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:16]}"


def clean_judgment_text(text: str, title: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.fullmatch(r"\[\[PAGE \d+\]\]", line):
            cleaned_lines.append(line)
            continue
        if not line:
            cleaned_lines.append("")
            continue
        if re.match(r"(?i)^indian kanoon\s+-\s+https?://", line):
            continue
        if title and line.lower().startswith(title.lower()[:60]) and "indian kanoon" in line.lower():
            continue
        if re.match(r"(?i)^(signature not verified|digitally signed by|reason:|date:)\s*$", line):
            continue
        cleaned_lines.append(line)
    return normalize_whitespace("\n".join(cleaned_lines))


CONTROLLING_ROLE_WEIGHTS = {
    "Material facts": 2.4,
    "Court reasoning": 3.0,
    "Operative order": 3.2,
    # A repeated unlabelled passage may still contain the governing enactment,
    # especially in older judgments whose section headings were lost in OCR.
    "Judgment passage": 0.55,
    # What a party argues, or what an earlier judgment says, is not necessarily
    # the law or factual finding governing the current case.
    "Party submissions": 0.0,
    "Cited authorities": 0.0,
}


def classify_passage_role(value: str, index: int, total: int) -> str:
    """Classify a passage without treating quoted precedent as the present holding."""

    lowered = value.lower()
    operative_signal = bool(
        re.search(
            r"\b(?:appeal|petition|application)\s+(?:is|stands)\s+(?:allowed|dismissed|disposed(?:\s+of)?)|"
            r"\b(?:impugned\s+)?(?:judgment|order|proceedings)\b.{0,80}\bquashed\s+and\s+set\s+aside\b|"
            r"\b(?:we|this court)\s+(?:allow|dismiss|dispose\s+of)\s+(?:the\s+)?(?:appeal|petition|application)\b|"
            r"\b(?:matter|case)\s+is\s+remand(?:ed)?\b",
            lowered,
            re.S,
        )
    )
    if index >= max(1, total - 3) and operative_signal:
        return "Operative order"

    present_case_signal = bool(
        re.search(
            r"\b(?:in\s+the\s+(?:present|instant)\s+(?:case|appeal|petition)|case\s+at\s+hand)\b|"
            r"\b(?:in\s+our|our\s+considered)\s+view\b|"
            r"\bfor\s+(?:the\s+)?(?:above|aforesaid|foregoing)\s+reasons\b|"
            r"\bwe\s+have\s+(?:heard|considered|examined)\b|"
            r"\bthe\s+impugned\s+(?:judgment|order)\b",
            lowered,
            re.S,
        )
    )
    current_holding_signal = bool(
        re.search(
            r"\bwe\s+(?:therefore\s+|accordingly\s+)?(?:hold|find|conclude|"
            r"are\s+of\s+the\s+(?:considered\s+)?view|do\s+not\s+agree|"
            r"are\s+unable\s+to\s+(?:agree|accept)|(?:reject|accept)\s+the\s+contention)\b",
            lowered,
            re.S,
        )
    )
    current_court_signal = present_case_signal or current_holding_signal
    party_submission_signal = bool(
        re.search(
            r"\b(?:learned\s+)?counsel\s+for\s+(?:the\s+)?(?:appellant|applicant|petitioner|"
            r"respondent|state|accused)[^.\n]{0,180}\b(?:submitted|contended|argued|urged)\b|"
            r"\b(?:it\s+was|counsel)\s+(?:further\s+)?(?:submitted|contended|argued)\b",
            lowered,
            re.S,
        )
    )

    case_name_count = len(
        re.findall(
            r"\b[A-Z][A-Za-z0-9.&'()/-]*(?:\s+[A-Z][A-Za-z0-9.&'()/-]*){0,6}"
            r"\s+(?:v\.?|vs\.?|versus)\s+[A-Z][A-Za-z0-9.&'()/-]*",
            value,
        )
    )
    reported_citation_count = len(
        re.findall(
            r"(?:\(?(?:19|20)\d{2}\)?\s*(?:\d+\s*)?(?:SCC(?:\s+OnLine)?|SCR|INSC|"
            r"Cri\.?\s*L\.?\s*J\.?|All\s+ER|WLR)\s*[:()A-Z-]*\s*\d+|"
            r"AIR\s+(?:19|20)\d{2}\s+[A-Z]{1,12}\s+\d+)",
            value,
            re.I,
        )
    )
    authority_lead_count = len(
        re.findall(
            r"\b(?:reliance\s+(?:was\s+)?placed\s+on|relied\s+(?:up)?on|following\s+(?:decisions|judgments)|"
            r"decision\s+(?:rendered\s+)?in|judgment\s+in|reported\s+in|referred\s+to\s+as|"
            r"in\s+the\s+case\s+of|we\s+may\s+(?:refer|advert)\s+to|reference\s+may\s+be\s+made\s+to|"
            r"this\s+court\s+in|supra)\b",
            lowered,
        )
    )
    direct_authority_quote = bool(
        re.search(
            r"\b(?:in\s+the\s+case\s+of|in|decision\s+in)\s+[^.\n]{3,140}\s+"
            r"(?:v\.?|vs\.?|versus)\s+[^.\n]{2,140}[,.]\s*"
            r"(?:this\s+court|the\s+(?:court|bench))\s+(?:held|observed|stated|ruled)\b|"
            r"\bthis\s+court\s+in\s+[^.\n]{3,180}\s+(?:v\.?|vs\.?|versus)\s+"
            r"[^.\n]{2,180}\s+(?:held|observed|stated|ruled)\b|"
            r"\b(?:held|observed)\s+(?:as\s+follows|thus)\s*:",
            lowered,
            re.S,
        )
    )
    citation_dominated = (
        direct_authority_quote
        or case_name_count >= 3
        or (case_name_count >= 1 and reported_citation_count + authority_lead_count >= 2)
        or (reported_citation_count >= 3 and authority_lead_count >= 1)
    )

    if party_submission_signal and not current_court_signal:
        return "Party submissions"
    if re.search(r"\b(?:brief facts|facts of the case|factual background|material facts)\b", lowered):
        return "Material facts"
    if citation_dominated and not present_case_signal and not (
        current_holding_signal and not direct_authority_quote
    ):
        return "Cited authorities"
    if current_court_signal or re.search(
        r"\b(?:we\s+(?:hold|find|conclude|are\s+of\s+the\s+view)|therefore|accordingly)\b",
        lowered,
    ):
        return "Court reasoning"
    return "Judgment passage"


def _controlling_metadata(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Select likely governing metadata independently from whole-document mentions."""

    string_fields = ("legalDomains", "statutes", "sections", "postures", "reliefs")
    scores: dict[str, dict[str, dict[str, Any]]] = {field: {} for field in string_fields}
    pair_scores: dict[tuple[str, str], dict[str, Any]] = {}
    fact_scores: dict[tuple[str, str], dict[str, Any]] = {}

    def record(
        target: dict[Any, dict[str, Any]],
        key: Any,
        display: Any,
        weight: float,
        chunk_index: int,
    ) -> None:
        if not key or weight <= 0:
            return
        entry = target.setdefault(
            key,
            {"display": display, "score": 0.0, "support": 0, "strongest": 0.0, "opening": False},
        )
        entry["score"] += weight
        entry["support"] += 1
        entry["strongest"] = max(entry["strongest"], weight)
        entry["opening"] = entry["opening"] or chunk_index <= 2

    for chunk_index, chunk in enumerate(chunks, start=1):
        role = str(chunk.get("section", "Judgment passage"))
        weight = CONTROLLING_ROLE_WEIGHTS.get(role, 0.0)
        if role == "Judgment passage" and chunk_index <= 2:
            weight *= 1.6
        if weight <= 0:
            continue
        for field in string_fields:
            for raw_value in chunk.get(field, []):
                value = str(raw_value).strip()
                record(scores[field], value.casefold(), value, weight, chunk_index)
        for raw_pair in chunk.get("provisionPairs", []):
            if not isinstance(raw_pair, dict):
                continue
            statute = str(raw_pair.get("statute", "")).strip()
            section = str(raw_pair.get("section", "")).strip()
            if not statute or not section:
                continue
            key = (statute.casefold(), section.casefold())
            record(
                pair_scores,
                key,
                {"statute": statute, "section": section},
                weight,
                chunk_index,
            )
        for raw_fact in chunk.get("materialFacts", []):
            if not isinstance(raw_fact, dict):
                continue
            name = str(raw_fact.get("name", "")).strip()
            value = str(raw_fact.get("value", "")).strip()
            if not name or not value:
                continue
            key = (name.casefold(), value.casefold())
            record(
                fact_scores,
                key,
                {"name": name, "value": value},
                weight,
                chunk_index,
            )

    def select(target: dict[Any, dict[str, Any]], limit: int) -> list[Any]:
        qualified = [
            entry
            for entry in target.values()
            if entry["strongest"] >= 2.0
            or (entry["support"] >= 2 and entry["score"] >= 1.0)
            or (entry["opening"] and entry["score"] >= 0.7)
        ]
        qualified.sort(
            key=lambda entry: (
                -entry["score"],
                -entry["support"],
                str(entry["display"]).casefold(),
            )
        )
        return [entry["display"] for entry in qualified[:limit]]

    return {
        "controllingLegalDomains": select(scores["legalDomains"], 6),
        "controllingStatutes": select(scores["statutes"], 8),
        "controllingSections": select(scores["sections"], 12),
        "controllingProvisionPairs": select(pair_scores, 10),
        "controllingPostures": select(scores["postures"], 6),
        "controllingReliefs": select(scores["reliefs"], 8),
        "controllingMaterialFacts": select(fact_scores, 16),
    }


def chunk_text(text: str, title: str, citation: str, issues: list[str]) -> list[dict[str, Any]]:
    page_marker = re.compile(r"^\[\[PAGE (\d+)\]\]$")
    segments: list[tuple[str, str]] = []
    page = "Unknown page"
    buffer: list[str] = []

    def flush(keep_overlap: bool = False) -> None:
        nonlocal buffer
        value = normalize_whitespace("\n".join(buffer))
        if len(value) >= 180:
            segments.append((page, value))
        if keep_overlap and value:
            words = value.split()
            overlap: list[str] = []
            overlap_length = 0
            for word in reversed(words):
                overlap.insert(0, word)
                overlap_length += len(word) + 1
                if overlap_length >= 320:
                    break
            buffer = [" ".join(overlap)]
        else:
            buffer = []

    for line in text.splitlines():
        marker = page_marker.match(line.strip())
        if marker:
            flush()
            page = f"PDF page {marker.group(1)}"
            continue
        buffered_length = sum(len(item) for item in buffer)
        if re.match(r"^\s*\d{1,3}[.)]\s+", line) and buffered_length >= 1_100:
            flush(keep_overlap=True)
        buffer.append(line)
        if sum(len(item) for item in buffer) >= 2_200:
            flush(keep_overlap=True)
    flush()

    chunks: list[dict[str, Any]] = []
    for index, (page_label, value) in enumerate(segments, start=1):
        chunks.append(
            {
                "id": f"passage-{index}",
                "section": classify_passage_role(value, index, len(segments)),
                "paragraph": page_label,
                "evidence": value.strip(),
            }
        )
    return chunks


def build_outputs(documents: list[ExtractedPdf]) -> dict[str, Any]:
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
    seen_hashes: dict[str, str] = {}
    manifest_rows: list[dict[str, str]] = []
    qa_rows: list[dict[str, str | int | float]] = []
    cases: list[dict[str, Any]] = []

    for document in documents:
        court = parse_court(document)
        judgment_date = parse_date(document)
        title = parse_title(document)
        citation = parse_citation(document)
        case_number = parse_case_number(document)
        source_url = parse_source_url(document)
        issues = classify_issues(document.text)
        identifier = stable_id(document, court, citation, case_number)
        duplicate_of = seen_hashes.get(document.sha256, "")
        seen_hashes.setdefault(document.sha256, identifier)

        manifest_rows.append(
            {
                "id": identifier,
                "title": title,
                "court": court,
                "date": judgment_date,
                "citation": citation,
                "case_number": case_number,
                "issues": " | ".join(issues),
                "source_url": source_url,
                "pdf_filename": document.relative_path,
            }
        )

        missing = [
            field
            for field, value in {
                "title": title,
                "date": judgment_date,
                "citation": citation,
                "case_number": case_number,
                "source_url": source_url,
            }.items()
            if not value
        ]
        warnings = list(document.warnings)
        suspicious_title = bool(
            title.startswith("CNR ")
            or re.search(r"(?i)^(?:AT\s+JAMMU|BENCH\s+AT|CT\.?\s*NO|CONSTITUTIONAL\s+WRIT\s+JURISDICTION|CIVIL\s+APPELLATE\s+JURISDICTION)\b", title)
            or len(title) < 6
            or re.search(r"(?i)\b(?:pin\s*-?\s*\d{6}|r/o|page\s+\d+\s+of)\b", title)
        )
        if suspicious_title:
            warnings.append("title_requires_review")
        if duplicate_of:
            warnings.append(f"duplicate_of:{duplicate_of}")
        indexable = document.quality >= 0.42 and len(document.text) >= 500 and not duplicate_of
        if not indexable:
            warnings.append("excluded_from_index")
        if missing:
            warnings.append("missing_metadata")
        status = "accepted" if indexable and not missing else "review_required" if indexable else "excluded"
        qa_rows.append(
            {
                "id": identifier,
                "status": status,
                "extraction_method": document.extraction_method,
                "text_quality": round(document.quality, 4),
                "pages": document.pages,
                "missing_fields": " | ".join(missing),
                "warnings": " | ".join(dict.fromkeys(warnings)),
                "content_sha256": document.sha256,
                "pdf_filename": document.relative_path,
            }
        )

        if indexable:
            cleaned = clean_judgment_text(document.text, title)
            chunks = chunk_text(cleaned, title, citation, issues)
            if chunks:
                for chunk in chunks:
                    chunk_profile = analyze_legal_query(
                        str(chunk["evidence"]), infer_intent=False
                    )
                    chunk["legalDomains"] = list(chunk_profile.domains)
                    chunk["statutes"] = list(chunk_profile.statutes)
                    chunk["sections"] = list(chunk_profile.sections)
                    chunk["provisionPairs"] = [
                        {"statute": statute, "section": section}
                        for statute, section in chunk_profile.provision_pairs
                    ]
                    chunk["postures"] = list(chunk_profile.postures)
                    chunk["reliefs"] = list(chunk_profile.reliefs)
                    chunk["materialFacts"] = [
                        {"name": name, "value": value}
                        for name, value in chunk_profile.facts
                    ]
                controlling_metadata = _controlling_metadata(chunks)
                legal_profile = analyze_legal_query(cleaned, infer_intent=False)
                disposition = extract_disposition(cleaned)
                case_stage = extract_case_stage(
                    cleaned,
                    f"Judgment or order in {case_number or 'case number not extracted'}",
                    issues,
                )
                bench = infer_bench_strength(cleaned)
                cases.append(
                    {
                        "id": identifier,
                        "title": title,
                        "court": "Supreme Court" if court == "Supreme Court" else "High Court",
                        "courtName": court,
                        "year": int(judgment_date[:4]) if judgment_date else 0,
                        "date": judgment_date,
                        "category": issues[0],
                        "citation": citation or "Citation not extracted - verify source document",
                        "posture": f"Judgment or order in {case_number or 'case number not extracted'}",
                        "legalIssues": issues,
                        "legalDomains": list(legal_profile.domains),
                        "statutes": list(legal_profile.statutes),
                        "sections": list(legal_profile.sections),
                        "provisionPairs": [
                            {"statute": statute, "section": section}
                            for statute, section in legal_profile.provision_pairs
                        ],
                        "postures": list(legal_profile.postures),
                        "reliefs": list(legal_profile.reliefs),
                        "partyRelationships": list(legal_profile.relationships),
                        "materialFacts": [
                            {"name": name, "value": value}
                            for name, value in legal_profile.facts
                        ],
                        **controlling_metadata,
                        "sourceUrl": source_url,
                        "pdfPath": document.relative_path,
                        "matterStatus": disposition.matter_status,
                        "trialStatus": disposition.trial_status,
                        "winner": disposition.winner,
                        "caseOutcome": disposition.case_outcome,
                        "outcomeRelief": disposition.outcome_relief,
                        "outcomeEvidence": disposition.evidence,
                        "caseStage": case_stage.stage,
                        "caseStageConfidence": case_stage.confidence,
                        "caseStageEvidence": case_stage.evidence,
                        "benchStrength": bench.label,
                        "benchSize": bench.size,
                        "benchEvidence": bench.evidence,
                        "chunks": [{**chunk, "id": f"{identifier}-{chunk['id']}"} for chunk in chunks],
                    }
                )

    manifest_rows.sort(key=lambda row: (row["court"], row["date"], row["title"], row["id"]))
    qa_rows.sort(key=lambda row: (str(row["status"]), str(row["pdf_filename"])))
    cases.sort(key=lambda case: (case["court"], case["date"], case["title"], case["id"]))

    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)
    with QA_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        fieldnames = ["id", "status", "extraction_method", "text_quality", "pages", "missing_fields", "warnings", "content_sha256", "pdf_filename"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(qa_rows)

    corpus = {
        "corpusVersion": f"import-{date.today().isoformat()}-{len(cases)}-cases",
        "description": "Generated source-document corpus. Review QA flags before institutional use.",
        "cases": cases,
    }
    CORPUS_PATH.write_text(
        json.dumps(corpus, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "documents": len(documents),
        "indexableCases": len(cases),
        "chunks": sum(len(case["chunks"]) for case in cases),
        "accepted": sum(row["status"] == "accepted" for row in qa_rows),
        "reviewRequired": sum(row["status"] == "review_required" for row in qa_rows),
        "excluded": sum(row["status"] == "excluded" for row in qa_rows),
        "ocrDocuments": sum(doc.extraction_method == "ocr" for doc in documents),
        "manifest": str(MANIFEST_PATH),
        "qaReport": str(QA_PATH),
        "corpus": str(CORPUS_PATH),
    }
