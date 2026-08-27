from __future__ import annotations

import re
from dataclasses import dataclass


VERIFY = "Not stated - verify judgment"


@dataclass(frozen=True)
class Disposition:
    matter_status: str
    trial_status: str
    winner: str
    case_outcome: str
    outcome_relief: str
    evidence: str


@dataclass(frozen=True)
class CaseStage:
    stage: str
    confidence: str
    evidence: str


@dataclass(frozen=True)
class BenchStrength:
    label: str
    size: int
    evidence: str


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\[\[PAGE \d+\]\]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=(?:\d{1,3}[.)]\s+|[A-Z]))", cleaned)
    return [part.strip() for part in parts if len(part.strip()) >= 35]


def _last_matching_sentence(sentences: list[str], patterns: tuple[str, ...]) -> str:
    for sentence in reversed(sentences):
        lowered = sentence.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            return sentence[:650]
    return ""


def _last_matching_sentence_with_index(
    sentences: list[str], patterns: tuple[str, ...]
) -> tuple[int, str]:
    for index in range(len(sentences) - 1, -1, -1):
        sentence = sentences[index]
        lowered = sentence.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            return index, sentence[:650]
    return -1, ""


def extract_trial_status(text: str) -> str:
    lowered = text.lower()
    ongoing_patterns = (
        r"\btrial (?:is|remains|was) pending\b",
        r"\bpending (?:the )?trial\b",
        r"\btrial (?:shall|may|must) (?:continue|proceed|commence)\b",
        r"\bexpedit(?:e|ed|iously)[^.!?]{0,80}\btrial\b",
        r"\btrial[^.!?]{0,100}\b(?:not likely|unlikely|no likelihood)[^.!?]{0,30}\b(?:conclude|complete|completed)\b",
        r"\bretrial\b",
    )
    completed_patterns = (
        r"\bafter (?:the )?conclusion of (?:the )?trial\b",
        r"\btrial (?:resulted|culminated) in\b",
        r"\btrial court (?:has )?(?:convicted|acquitted)\b",
        r"\bjudgment of conviction\b",
        r"\border of acquittal\b",
    )
    ongoing_match = max(
        (match.start() for pattern in ongoing_patterns for match in re.finditer(pattern, lowered)),
        default=-1,
    )
    completed_match = max(
        (match.start() for pattern in completed_patterns for match in re.finditer(pattern, lowered)),
        default=-1,
    )
    if ongoing_match >= 0 and ongoing_match > completed_match:
        return "Trial ongoing"
    if completed_match >= 0:
        return "Trial completed"
    return VERIFY


def extract_case_stage(
    text: str,
    posture: str = "",
    legal_issues: list[str] | None = None,
) -> CaseStage:
    """Classify procedural stage from the complete available judgment text."""

    sentences = _sentences(text)
    combined = f"{posture}. {text}"
    rules: list[tuple[str, tuple[str, ...], str]] = [
        (
            "Remanded / retrial ordered",
            (
                r"\bremand(?:ed)? (?:the )?(?:case|matter|proceedings?)\b",
                r"\bremit(?:ted)? (?:the )?(?:case|matter|proceedings?)\b",
                r"\bfresh trial\b",
                r"\bretrial (?:is )?ordered\b",
            ),
            "High",
        ),
        (
            "Trial completed - acquitted",
            (
                r"\btrial court (?:has )?acquitted\b",
                r"\border of acquittal\b",
                r"\bwas acquitted (?:by|after)\b",
            ),
            "High",
        ),
        (
            "Trial completed - convicted",
            (
                r"\btrial court (?:has )?convicted\b",
                r"\bjudgment of conviction\b",
                r"\bwas convicted (?:by|after)\b",
            ),
            "High",
        ),
        (
            "Trial ongoing",
            (
                r"\btrial (?:is|remains|was) pending\b",
                r"\bpending (?:the )?trial\b",
                r"\btrial (?:shall|may|must) (?:continue|proceed|commence)\b",
                r"\btrial[^.!?]{0,100}\b(?:not likely|unlikely|no likelihood)[^.!?]{0,30}\b(?:conclude|complete|completed)\b",
                r"\bonly \d+[^.!?]{0,50}\bwitness(?:es)? (?:has|have) been examined\b",
            ),
            "High",
        ),
        (
            "Investigation ongoing",
            (
                r"\binvestigation (?:is|remains) (?:pending|incomplete|ongoing)\b",
                r"\bfurther investigation (?:is|was|shall be) (?:pending|ongoing|conducted)\b",
                r"\bcharge[ -]?sheet (?:has )?not (?:yet )?been filed\b",
            ),
            "High",
        ),
    ]

    candidates: list[tuple[int, int, str, str, str]] = []
    for priority, (stage, patterns, confidence) in enumerate(rules):
        sentence_index, evidence = _last_matching_sentence_with_index(sentences, patterns)
        if evidence:
            candidates.append((sentence_index, -priority, stage, confidence, evidence))
    if candidates:
        _, _, stage, confidence, evidence = max(candidates)
        return CaseStage(stage, confidence, evidence)

    appeal_patterns = (
        r"\b(?:criminal|civil) appeals?\b",
        r"\bappeals? no(?:\.|s\.)?\b",
        r"\brevision (?:petition|application)\b",
        r"\brevisional jurisdiction\b",
    )
    appeal_evidence = _last_matching_sentence(_sentences(combined[:15_000]), appeal_patterns)
    if appeal_evidence or re.search(r"(?i)\b(?:appeal|revision)\b", posture):
        return CaseStage(
            "Appeal / revision stage",
            "Medium",
            appeal_evidence or posture,
        )

    issues = set(legal_issues or [])
    criminal_issues = {
        "Criminal Law", "Regular Bail", "Anticipatory Bail", "Default Bail",
        "Prolonged Custody", "Narcotics / NDPS", "Economic Offences / PMLA",
        "Cheque Dishonour", "Quashing of Criminal Proceedings",
    }
    if issues and not issues.intersection(criminal_issues):
        return CaseStage("Not applicable", "Medium", posture or "No criminal trial issue was classified.")

    disposed_evidence = _last_matching_sentence(
        sentences,
        (r"\b(?:appeal|petition|application|matter)[^.!?]{0,80}\bdisposed of\b",),
    )
    if disposed_evidence:
        return CaseStage("Matter disposed", "High", disposed_evidence)
    return CaseStage("Not clearly stated", "Low", "No unambiguous stage wording was extracted.")


def infer_bench_strength(text: str) -> BenchStrength:
    lowered = text.lower()
    explicit = [
        (r"\b(?:constitution|constitutional) bench\b", "Constitution Bench", 5),
        (r"\bfive[- ]judge bench\b", "Five-judge bench", 5),
        (r"\bthree[- ]judge bench\b", "Three-judge bench", 3),
        (r"\bdivision bench\b", "Division bench", 2),
        (r"\bsingle judge\b", "Single judge", 1),
    ]
    for pattern, label, size in explicit:
        match = re.search(pattern, lowered)
        if match:
            sentence = _last_matching_sentence(_sentences(text), (pattern,))
            return BenchStrength(label, size, sentence or match.group(0))

    bench_line = re.search(r"(?im)^\s*bench\s*:\s*([^\r\n]{3,300})", text[:12_000])
    if bench_line:
        raw_names = bench_line.group(1).strip()
        names = [
            name.strip(" .,-")
            for name in re.split(r"\s*(?:,|\band\b|&)\s*", raw_names, flags=re.I)
            if name.strip(" .,-")
        ]
        if names:
            size = min(len(names), 9)
            label = "Single judge" if size == 1 else "Division bench" if size == 2 else f"{size}-judge bench"
            return BenchStrength(label, size, f"Bench: {raw_names}")

    names = {
        re.sub(r"\s+", " ", name).strip(" .,-")
        for name in re.findall(
            r"(?im)(?:hon['’]?ble\s+)?(?:mr\.?\s+|ms\.?\s+)?justice\s+([a-z][a-z .'-]{2,60})",
            text[:12_000],
        )
    }
    names = {name for name in names if len(name.split()) <= 8}
    if names:
        size = min(len(names), 9)
        label = "Single judge" if size == 1 else "Division bench" if size == 2 else f"{size}-judge bench"
        return BenchStrength(label, size, "; ".join(sorted(names))[:350])
    return BenchStrength("Bench size not extracted", 0, "No reliable bench-strength wording was extracted.")


def extract_disposition(text: str) -> Disposition:
    """Extract only conclusions supported by final-order language.

    This is deliberately conservative. A missing or ambiguous conclusion is exposed
    as a verification requirement rather than converted into a plausible winner.
    """

    tail = text[-12_000:]
    sentences = _sentences(tail)
    lowered = tail.lower()

    partial = (r"\bpartly allowed\b", r"\ballowed in part\b", r"\bpartially allowed\b")
    remand = (
        r"\bremand(?:ed)?\b",
        r"\bremit(?:ted)?\b",
        r"\brestored to (?:the file|its original number)\b",
        r"\bfresh (?:trial|consideration|decision)\b",
    )
    bail_granted = (
        r"\benlarged on (?:default )?bail\b",
        r"\breleased on (?:regular |default |anticipatory )?bail\b",
        r"\bbail (?:is )?granted\b",
        r"\bapplication for bail (?:is )?allowed\b",
    )
    bail_refused = (
        r"\bbail (?:is )?(?:rejected|refused|cancelled)\b",
        r"\bapplication for bail (?:is )?dismissed\b",
    )
    appeal_allowed = (r"\bappeals? (?:is|are|stands?|accordingly)?\s*allowed\b",)
    appeal_dismissed = (r"\bappeals? (?:is|are|stands?|accordingly)?\s*dismissed\b",)
    petition_allowed = (
        r"\b(?:petition|application|writ petition) (?:is|stands?|accordingly)?\s*allowed\b",
    )
    petition_dismissed = (
        r"\b(?:petition|application|writ petition) (?:is|stands?|accordingly)?\s*dismissed\b",
    )
    set_aside = (r"\b(?:impugned |said )?(?:order|judgment|conviction)[^.!?]{0,100}\bset aside\b",)
    disposed = (r"\b(?:appeal|petition|application|matter)[^.!?]{0,80}\bdisposed of\b",)

    rules: list[tuple[tuple[str, ...], str, str, str, str]] = [
        (partial, "Disposed", "Mixed / partial relief", "Case partly allowed", "Partial relief granted"),
        (remand, "Remanded", "No final winner - matter remanded", "Matter remanded for fresh decision", "Matter remanded; no final winner"),
        (bail_granted, "Disposed", "Accused / applicant succeeded", "Bail granted", "Bail granted to accused / applicant"),
        (bail_refused, "Disposed", "State / respondent succeeded", "Bail refused or cancelled", "Bail refused; State / respondent succeeded"),
        (appeal_allowed, "Disposed", "Appellant succeeded", "Appeal allowed", "Appeal allowed for appellant"),
        (appeal_dismissed, "Disposed", "Respondent succeeded", "Appeal dismissed", "Appeal dismissed; respondent succeeded"),
        (petition_allowed, "Disposed", "Petitioner / applicant succeeded", "Petition allowed", "Petition allowed for petitioner / applicant"),
        (petition_dismissed, "Disposed", "Respondent succeeded", "Petition dismissed", "Petition dismissed; respondent succeeded"),
        (set_aside, "Disposed", "Appellant / petitioner succeeded", "Impugned decision set aside", "Impugned decision set aside"),
    ]

    matter_status = VERIFY
    winner = VERIFY
    case_outcome = VERIFY
    outcome_relief = VERIFY
    evidence = ""
    candidates: list[tuple[int, int, str, str, str, str, str]] = []
    for priority, (patterns, status, rule_winner, outcome, relief) in enumerate(rules):
        sentence_index, sentence = _last_matching_sentence_with_index(sentences, patterns)
        if sentence:
            candidates.append((sentence_index, -priority, sentence, status, rule_winner, outcome, relief))
    if candidates:
        _, _, evidence, matter_status, winner, case_outcome, outcome_relief = max(candidates)
    if not evidence:
        evidence = _last_matching_sentence(sentences, disposed)
        if evidence:
            matter_status = "Disposed"
            case_outcome = "Matter disposed"
            outcome_relief = "Matter disposed; relief not clearly extracted"

    trial_status = extract_trial_status(tail)

    return Disposition(
        matter_status,
        trial_status,
        winner,
        case_outcome,
        outcome_relief,
        evidence or VERIFY,
    )


def build_case_summary(evidence: str, query: str, outcome_evidence: str = "") -> str:
    """Create a short extractive, query-focused summary without an LLM or API key."""

    sentences = _sentences(evidence)
    if not sentences:
        return evidence[:700].strip()

    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 3
        and token
        not in {"that", "this", "there", "their", "after", "before", "where", "which", "with", "from"}
    }
    legal_cues = {
        "allowed", "dismissed", "bail", "custody", "trial", "evidence", "investigation",
        "conviction", "acquittal", "witness", "abscond", "sentence", "relief",
    }
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        words = set(re.findall(r"[a-z0-9]+", sentence.lower()))
        score = 3 * len(words & query_tokens) + len(words & legal_cues)
        scored.append((score, index, sentence))

    chosen = sorted(sorted(scored, reverse=True)[:4], key=lambda item: item[1])
    summary_parts = [sentence for _, _, sentence in chosen]
    if outcome_evidence and outcome_evidence != VERIFY:
        normalized_outcome = re.sub(r"\s+", " ", outcome_evidence).strip()
        if normalized_outcome and not any(normalized_outcome in part or part in normalized_outcome for part in summary_parts):
            summary_parts.append(normalized_outcome)

    summary = " ".join(summary_parts)
    if len(summary) <= 850:
        return summary
    shortened = summary[:850].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}…"
