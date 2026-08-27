from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LegalQueryProfile:
    """Deterministic legal features shared by retrieval and transparent reranking."""

    concepts: tuple[str, ...]
    domains: tuple[str, ...]
    statutes: tuple[str, ...]
    sections: tuple[str, ...]
    provision_pairs: tuple[tuple[str, str], ...]
    postures: tuple[str, ...]
    reliefs: tuple[str, ...]
    relationships: tuple[str, ...]
    facts: tuple[tuple[str, str], ...]
    material_phrases: tuple[str, ...]
    quantities: tuple[str, ...]


LEGAL_CONCEPTS: dict[str, tuple[str, ...]] = {
    "Regular Bail": ("regular bail", "release pending trial", "pre-trial release", "section 439"),
    "Anticipatory Bail": ("anticipatory bail", "pre-arrest bail", "section 438"),
    "Default Bail": ("default bail", "statutory bail", "section 167(2)", "charge sheet deadline"),
    "Prolonged Custody": (
        "prolonged custody", "long detention", "long incarceration", "trial delay",
        "trial is unlikely to conclude", "trial unlikely to conclude", "custody for over two years",
        "remained in custody for over two years",
    ),
    "Documentary Evidence": ("documentary evidence", "paper trail", "official records"),
    "Witness Interference": ("witness interference", "witness tampering", "influence witnesses", "threatened witness"),
    "Flight Risk": ("flight risk", "abscond", "flee from justice"),
    "Investigation Complete": ("investigation complete", "charge sheet has been filed", "charge sheet filed", "challan filed"),
    "Personal Liberty": ("personal liberty", "article 21", "liberty"),
    "Economic Offence": ("economic offence", "money laundering", "pmla", "financial fraud"),
    "Quashing": ("quash the fir", "quashing of fir", "quashing of criminal proceedings", "section 482"),
    "Intestate Succession": ("intestate", "died without a will", "no will", "succession under section 8"),
    "Inheritance": ("inheritance", "inherited property", "legal heir", "legal heirs", "line of succession"),
    "Partition": ("partition", "division of property", "share in the property", "one half share", "equal share"),
    "Coparcenary": ("coparcenary", "coparcener", "ancestral property", "joint hindu family", "huf property"),
    "Testamentary Succession": ("testamentary succession", "last will", "probate", "letters of administration"),
    "Specific Performance": ("specific performance", "agreement to sell", "sale agreement"),
    "Landlord Tenant": ("landlord", "tenant", "tenancy", "eviction", "rent control"),
    "Arbitration": ("arbitration", "arbitral award", "arbitral tribunal", "patent illegality"),
    "Tax Assessment": ("income tax assessment", "assessment order", "tax deduction", "income tax"),
    "Service Dispute": ("service law", "seniority", "promotion", "disciplinary proceedings", "termination from service"),
    "Matrimonial Dispute": ("matrimonial", "divorce", "domestic violence", "maintenance", "hindu marriage act"),
    "Motor Accident Compensation": ("motor accident", "mact", "motor vehicles act", "accident compensation"),
    "Consumer Dispute": ("consumer protection", "consumer dispute", "deficiency in service"),
    "Insolvency": ("insolvency", "bankruptcy code", "ibc", "corporate debtor"),
    "Environmental Law": ("environment protection", "pollution control", "national green tribunal", "forest conservation"),
    "Cheque Dishonour": ("cheque dishonour", "dishonour of cheque", "dishonor of cheque", "section 138"),
}


DOMAIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "Bail / Criminal Procedure": (
        "bail / criminal procedure", "regular bail", "anticipatory bail", "default bail", "bail",
        "accused", "custody", "charge sheet", "fir", "crpc", "bnss", "criminal appeal",
    ),
    "Succession / Inheritance": (
        "hindu succession", "inheritance", "legal heir", "intestate", "last will", "probate",
        "died without a will", "without a valid will", "no valid will", "invalid will",
        "testamentary succession", "will of the deceased", "execution of the will",
        "coparcenary", "coparcener", "ancestral property", "class i heir",
    ),
    "Property / Land": (
        "property / land", "immovable property", "property dispute", "partition", "land acquisition", "transfer of property",
        "specific performance", "title to property",
    ),
    "Tenancy / Rent Control": (
        "landlord", "tenant", "tenancy", "eviction", "rent control", "rent tribunal",
        "rent controller",
    ),
    "Probate / Wills": (
        "probate", "letters of administration", "testamentary", "validity of the will",
        "execution of the will",
    ),
    "Family / Matrimonial": (
        "family / matrimonial", "matrimonial", "divorce", "domestic violence", "maintenance", "hindu marriage act", "spouse",
    ),
    "Arbitration": ("arbitration", "arbitral", "arbitrator", "patent illegality"),
    "Taxation": ("taxation", "income tax", "gst", "goods and services tax", "central excise", "customs act", "tax assessment"),
    "Service Law": ("service law", "seniority", "promotion", "disciplinary proceedings", "government employee"),
    "Constitutional Law": ("constitutional law", "constitution", "fundamental right", "article 14", "article 19", "article 21", "article 226"),
    "Consumer Law": ("consumer protection", "consumer dispute", "deficiency in service"),
    "Insolvency": ("insolvency", "bankruptcy code", "ibc", "corporate debtor"),
    "Motor Vehicles / Compensation": ("motor accident", "motor vehicles act", "mact", "accident compensation"),
    "Environmental Law": ("environment protection", "pollution", "national green tribunal", "forest conservation"),
    "Cheque Dishonour": ("cheque dishonour", "dishonour of cheque", "negotiable instruments", "section 138"),
    "Contract / Commercial": (
        "indian contract act", "breach of contract", "commercial dispute", "agreement to sell",
        "specific performance", "contractual obligation",
    ),
    "Company Law": (
        "companies act", "company law", "shareholder", "director of the company",
        "oppression and mismanagement", "nclt",
    ),
    "Banking / Recovery": (
        "sarfaesi", "debt recovery tribunal", "secured creditor", "bank guarantee",
        "recovery of debt",
    ),
    "Labour / Employment": (
        "industrial disputes act", "workman", "labour court", "retrenchment",
        "industrial tribunal",
    ),
    "Intellectual Property": (
        "trade marks act", "trademark infringement", "copyright act", "patents act",
        "passing off",
    ),
    "Criminal Substantive Law": (
        "indian penal code", "bharatiya nyaya sanhita", "murder", "culpable homicide",
        "criminal conspiracy", "cheating offence",
    ),
}


STATUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "Hindu Succession Act, 1956": ("hindu succession act", "hsa 1956"),
    "Code of Criminal Procedure, 1973": ("code of criminal procedure", "criminal procedure code", "crpc"),
    "Bharatiya Nagarik Suraksha Sanhita, 2023": ("bharatiya nagarik suraksha sanhita", "bnss"),
    "Indian Penal Code, 1860": ("indian penal code", "ipc"),
    "Bharatiya Nyaya Sanhita, 2023": ("bharatiya nyaya sanhita", "bns"),
    "Constitution of India": ("constitution of india",),
    "Code of Civil Procedure, 1908": ("code of civil procedure", "civil procedure code", "cpc"),
    "Indian Evidence Act, 1872": ("indian evidence act", "evidence act"),
    "Narcotic Drugs and Psychotropic Substances Act, 1985": ("narcotic drugs and psychotropic substances act", "ndps act", "ndps"),
    "Prevention of Money Laundering Act, 2002": ("prevention of money laundering act", "pmla"),
    "Arbitration and Conciliation Act, 1996": ("arbitration and conciliation act", "a & c act", "arbitration act"),
    "Transfer of Property Act, 1882": ("transfer of property act", "tp act"),
    "Negotiable Instruments Act, 1881": ("negotiable instruments act", "ni act"),
    "Insolvency and Bankruptcy Code, 2016": ("insolvency and bankruptcy code", "ibc"),
    "Motor Vehicles Act, 1988": ("motor vehicles act", "mv act"),
    "Hindu Marriage Act, 1955": ("hindu marriage act",),
    "Income-tax Act, 1961": ("income tax act", "income-tax act"),
    "Consumer Protection Act": ("consumer protection act",),
    "Specific Relief Act, 1963": ("specific relief act",),
    "Indian Contract Act, 1872": ("indian contract act", "contract act"),
    "Registration Act, 1908": ("registration act",),
    "Limitation Act, 1963": ("limitation act",),
    "Companies Act, 2013": ("companies act",),
    "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002": (
        "securitisation and reconstruction of financial assets and enforcement of security interest act",
        "sarfaesi act", "sarfaesi",
    ),
    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989": (
        "scheduled castes and scheduled tribes prevention of atrocities act", "sc/st act",
        "atrocities act",
    ),
    "Unlawful Activities (Prevention) Act, 1967": (
        "unlawful activities prevention act", "uapa",
    ),
    "Industrial Disputes Act, 1947": ("industrial disputes act",),
    "Real Estate (Regulation and Development) Act, 2016": (
        "real estate regulation and development act", "rera",
    ),
}


RELIEF_PATTERNS: dict[str, tuple[str, ...]] = {
    "Bail": ("bail", "release from custody"),
    "Quashing": ("quash", "set aside fir"),
    "Partition / declaration of share": ("partition", "declaration of share", "one half share", "equal share"),
    "Specific performance": ("specific performance",),
    "Injunction": ("injunction", "restrain the respondent"),
    "Compensation": ("compensation", "damages"),
    "Maintenance": ("maintenance", "alimony"),
    "Set aside order or award": ("set aside the order", "set aside the award", "award is challenged"),
    "Remand": ("remand the matter", "sent back for fresh consideration"),
    "Declaration of title": ("declaration of title", "declare the plaintiff as owner"),
    "Eviction / possession": (
        "eviction", "recover possession", "vacant possession", "ejectment",
    ),
    "Probate / letters of administration": ("grant probate", "letters of administration"),
    "Tax reassessment relief": (
        "quash the reassessment", "reopening of assessment", "set aside the assessment order",
    ),
}


POSTURE_PATTERNS: dict[str, tuple[str, ...]] = {
    "Bail application / appeal": (
        "bail application", "application for bail", "petition for bail", "grant of regular bail",
        "rejection of bail", "refusal of bail", "enlarged on bail",
    ),
    "Civil appeal": (
        "civil appeal", "first appeal", "second appeal", "appeal from the original decree",
        "appeal against the decree", "regular first appeal",
    ),
    "Criminal appeal": ("criminal appeal",),
    "Writ petition": ("writ petition", "writ jurisdiction", "article 226"),
    "Special leave petition": (
        "special leave petition", "slp (", "slp(", "slp no.", "slp no ",
    ),
    "Revision": ("revision petition", "criminal revision", "civil revision"),
    "Review": ("review petition", "review application"),
    "Arbitral-award challenge": ("challenge to the arbitral award", "set aside the award", "section 34 of the arbitration"),
    "Original civil proceeding": ("civil suit", "suit for partition", "suit for declaration", "original suit"),
}


RELATIONSHIP_PATTERNS: dict[str, tuple[str, ...]] = {
    "Siblings / co-heirs": (
        "two brothers", "brothers", "two sisters", "sisters", "brother and sister",
        "brother and a sister", "siblings", "co-heirs", "co heirs",
    ),
    "Parent and child": ("father and son", "father and daughter", "mother and son", "parent and child"),
    "Spouses": ("husband and wife", "wife and husband", "spouses", "married couple"),
    "Landlord and tenant": (
        "landlord and tenant", "tenant and landlord", "landlord-tenant", "tenancy dispute",
        "eviction of the tenant", "rent control",
    ),
    "Employer and employee": ("employer and employee", "employee", "service matter"),
    "Insurer and claimant": ("insurance company", "insurer", "claimant"),
}


FACT_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "investigation_status": {
        "complete": (
            "investigation is complete", "investigation completed", "investigation stands completed",
            "completed its investigation", "charge sheet has been filed", "charge sheet filed",
            "charge-sheet has already been filed", "charge-sheet has been filed",
            "filed the final report", "final report has been filed", "challan filed",
        ),
        "pending": (
            "investigation is pending", "investigation pending", "investigation is incomplete",
            "charge sheet not filed", "charge sheet has not been filed", "charge-sheet has not been filed",
            "no charge sheet", "final report has not been filed",
        ),
    },
    "trial_status": {
        "delayed": ("trial is unlikely to conclude", "trial unlikely to conclude", "trial delay", "trial is delayed", "prolonged trial"),
        "completed": (
            "trial has concluded", "trial is completed", "trial concluded", "convicted by the trial court",
            "acquitted by the trial court", "after trial", "on conclusion of the trial",
        ),
    },
    "custody_status": {
        "prolonged": (
            "prolonged custody", "long incarceration", "remained in custody for over",
            "custody for over two years", "custody for more than two years",
        ),
        "not_in_custody": ("was not arrested", "not arrested", "never arrested", "not in custody"),
    },
    "flight_risk": {
        "absent": (
            "no flight risk", "not a flight risk", "no risk of absconding", "may not abscond",
            "will not abscond", "not likely to abscond", "did not abscond", "has not absconded",
            "cannot abscond", "no possibility of absconding", "no likelihood of absconding",
            "no allegation that the accused may abscond", "no allegation that the applicant may abscond",
        ),
        "present": ("flight risk", "likely to abscond", "may abscond", "fled from justice", "absconding accused"),
    },
    "witness_interference": {
        "absent": (
            "no witness interference", "no risk of influencing witnesses", "will not influence witnesses",
            "may not influence witnesses", "no allegation that the accused may influence witnesses",
            "did not influence witnesses", "has not influenced witnesses", "not influence witnesses",
            "never intimidated a witness", "never intimidated witnesses", "has not threatened witnesses",
            "neither the accused nor his family has threatened witnesses",
            "no allegation that the applicant may influence witnesses",
            "no allegation that the accused may abscond or influence witnesses",
            "no allegation that the applicant may abscond or influence witnesses",
        ),
        "present": ("witness interference", "influence witnesses", "witness tampering", "threatened the witness", "threatened witnesses", "intimidated witnesses"),
    },
    "succession_mode": {
        "intestate": (
            "died intestate", "died without a will", "no will", "no valid will", "invalid will",
            "will was invalid", "will is invalid", "intestate succession",
        ),
        "testamentary": ("left a will", "executed a will", "valid will", "testamentary succession", "probate of the will"),
    },
    "personal_law": {
        "hindu": ("hindu succession act", "hindu law", "mitakshara", "coparcenary"),
        "muslim": ("muslim personal law", "mohammedan law", "mahomedan law", "sunni law", "shia law"),
    },
    "property_character": {
        "self_acquired": (
            "self-acquired property", "self acquired property", "separate property",
            "absolute property of the deceased",
        ),
        "ancestral_coparcenary": (
            "ancestral property", "coparcenary property", "joint hindu family property",
            "huf property",
        ),
    },
    "prior_partition": {
        "completed": ("prior partition", "partition had already taken place", "partition was effected"),
        "absent": ("no prior partition", "property remained undivided", "no partition had taken place"),
    },
    "will_status": {
        "invalid_or_absent": (
            "no valid will", "invalid will", "will was invalid", "will is invalid",
            "revoked will", "died without a will", "no will",
        ),
        "valid": ("valid will", "duly executed will", "proved the will", "probate of the will"),
    },
    "evidence_type": {
        "documentary": ("documentary evidence", "official records", "paper trail"),
        "oral_or_eyewitness": ("oral evidence", "eye-witness", "eyewitness testimony", "ocular evidence"),
    },
}


MATERIAL_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "has", "have", "having", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "there", "this", "to", "under", "was", "were", "which", "with", "would",
    "case", "court", "judgment", "order", "learned", "honble", "petitioner", "respondent",
}

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}


def _contains_phrase(text: str, phrase: str) -> bool:
    if " " in phrase or len(phrase) > 5:
        return phrase in text
    if re.fullmatch(r"[a-z0-9]+", phrase):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))
    return phrase in text


def _matched_labels(text: str, patterns: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(
        label
        for label, variants in patterns.items()
        if any(_contains_phrase(text, variant) for variant in variants)
    )


def extract_sections(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    provisions = re.findall(
        r"\b(?:sections?|secs?\.?|s\.?|u/s)\s*[-:]?\s*(\d+[a-z]?(?:\s*\([a-z0-9]+\))*)",
        lowered,
    )
    articles = re.findall(r"\barticles?\s*[-:]?\s*(\d+[a-z]?(?:\s*\([a-z0-9]+\))*)", lowered)
    normalized = [f"Section {re.sub(r'\s+', '', item).upper()}" for item in provisions]
    normalized.extend(f"Article {re.sub(r'\s+', '', item).upper()}" for item in articles)
    return tuple(dict.fromkeys(normalized))


def extract_statutes(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    matched = [
        statute
        for statute, aliases in STATUTE_ALIASES.items()
        if any(_contains_phrase(lowered, alias) for alias in aliases)
    ]
    return tuple(dict.fromkeys(matched))


def extract_provision_pairs(text: str) -> tuple[tuple[str, str], ...]:
    """Associate provisions with Acts in the same sentence or short clause."""

    lowered = re.sub(r"\s+", " ", text.lower())
    pairs: list[tuple[str, str]] = []
    for segment in re.split(r"(?<=[.;:])\s+|\n+|\b(?:while|whereas|but)\b", lowered):
        if len(segment) > 900:
            continue
        statutes = extract_statutes(segment)
        sections = extract_sections(segment)
        # Pair freely only when one side is unambiguous.  Cross-producing two
        # Acts and two section numbers silently equates unrelated provisions
        # (for example Section 8 HSA and Section 8 Arbitration Act).
        if statutes and sections and (len(statutes) == 1 or len(sections) == 1):
            pairs.extend((statute, section) for statute in statutes for section in sections)
    all_statutes = extract_statutes(lowered)
    all_sections = extract_sections(lowered)
    if len(all_statutes) == 1:
        pairs.extend((all_statutes[0], section) for section in all_sections)
    return tuple(dict.fromkeys(pairs))


def extract_material_phrases(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    phrases: list[str] = []
    for size in (3, 2):
        for index in range(0, len(tokens) - size + 1):
            window = tokens[index : index + size]
            if any(token in MATERIAL_STOPWORDS for token in window):
                continue
            if all(len(token) <= 2 and not token.isdigit() for token in window):
                continue
            phrase = " ".join(window)
            if phrase not in phrases:
                phrases.append(phrase)
            if len(phrases) >= 24:
                return tuple(phrases)
    return tuple(phrases)


def extract_quantities(text: str) -> tuple[str, ...]:
    lowered = re.sub(r"\bone[ -]half\b", "1/2", text.lower())
    lowered = re.sub(r"\bone[ -]third\b", "1/3", lowered)
    lowered = re.sub(r"\btwo[ -]thirds?\b", "2/3", lowered)
    for word, number in NUMBER_WORDS.items():
        lowered = re.sub(rf"\b{word}\b", number, lowered)
    quantities: list[str] = []
    pattern = re.compile(
        r"\b(\d+(?:\.\d+)?(?:/\d+)?)\s*(years?|months?|days?|shares?|percent|per cent|%)?\b"
    )
    for match in pattern.finditer(lowered):
        value, unit = match.group(1), match.group(2) or ""
        prefix = lowered[max(0, match.start() - 16) : match.start()]
        if re.search(r"(?:section|article|act|of)\s*$", prefix):
            continue
        # Only a four-digit integer can be a calendar year.  Decimal amounts
        # such as ``4.11`` previously reached ``int(value)`` and could crash a
        # live search while candidate passages were being analysed.
        if not unit and value.isdigit() and len(value) == 4 and 1900 <= int(value) <= 2100:
            continue
        normalized_unit = "percent" if unit in {"per cent", "%"} else unit.rstrip("s")
        quantities.append(f"{value} {normalized_unit}".strip())
    return tuple(dict.fromkeys(quantities))


def extract_facts(text: str) -> tuple[tuple[str, str], ...]:
    lowered = text.lower()
    facts: list[tuple[str, str]] = []
    for name, values in FACT_PATTERNS.items():
        matched_values: list[tuple[int, str]] = []
        for value, variants in values.items():
            positions = [lowered.find(variant) for variant in variants if _contains_phrase(lowered, variant)]
            if positions:
                matched_values.append((min(position for position in positions if position >= 0), value))
        if matched_values:
            # If a passage discusses multiple legal regimes or both sides of a
            # factual issue, use the first explicit formulation as the passage's
            # primary signal. Query-side negative phrases are intentionally listed
            # in full, so their position precedes the positive words they contain.
            facts.append((name, min(matched_values)[1]))
    return tuple(facts)


def analyze_legal_query(text: str, *, infer_intent: bool = True) -> LegalQueryProfile:
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    # "Tenants in common" and "co-tenants" describe concurrent ownership,
    # especially in succession/partition cases; they are not rent-control
    # relationships.  Remove those phrases only for catalog classification so
    # that the original wording remains available to facts and phrase matching.
    catalog_text = re.sub(
        r"\b(?:tenants?\s*(?:-|–|—)?\s*in\s*(?:-|–|—)?\s*common|co\s*(?:-|–|—)?\s*tenants?|joint\s+tenants?)\b",
        "co owners",
        lowered,
    )
    concepts = list(_matched_labels(catalog_text, LEGAL_CONCEPTS))
    domains = list(_matched_labels(catalog_text, DOMAIN_PATTERNS))
    reliefs = list(_matched_labels(lowered, RELIEF_PATTERNS))
    facts = extract_facts(lowered)
    fact_values = dict(facts)
    if fact_values.get("flight_risk") == "absent" and "Flight Risk" in concepts:
        concepts.remove("Flight Risk")
    if (
        fact_values.get("witness_interference") == "absent"
        and "Witness Interference" in concepts
    ):
        concepts.remove("Witness Interference")
    # Plain-language bail descriptions often omit the word "bail" entirely.
    # A combination of accused/applicant + custody + pending/delayed trial is a
    # conservative signal that release pending trial is the relief being sought.
    implied_bail = (
        ("accused" in lowered or "applicant" in lowered)
        and ("custody" in lowered or "incarcerat" in lowered or "detention" in lowered)
        and ("trial" in lowered or "investigation" in lowered or "charge sheet" in lowered)
    )
    if infer_intent and implied_bail:
        if "Regular Bail" not in concepts:
            concepts.append("Regular Bail")
        if "Bail / Criminal Procedure" not in domains:
            domains.append("Bail / Criminal Procedure")
        if "Bail" not in reliefs:
            reliefs.append("Bail")
    return LegalQueryProfile(
        concepts=tuple(concepts),
        domains=tuple(domains),
        statutes=extract_statutes(lowered),
        sections=extract_sections(lowered),
        provision_pairs=extract_provision_pairs(lowered),
        postures=_matched_labels(lowered, POSTURE_PATTERNS),
        reliefs=tuple(reliefs),
        relationships=_matched_labels(lowered, RELATIONSHIP_PATTERNS),
        facts=facts,
        material_phrases=extract_material_phrases(lowered),
        quantities=extract_quantities(lowered),
    )


def profile_signals(profile: LegalQueryProfile) -> list[str]:
    values = [
        *profile.concepts,
        *profile.domains,
        *profile.statutes,
        *profile.sections,
        *(f"{section} — {statute}" for statute, section in profile.provision_pairs),
        *profile.postures,
        *profile.reliefs,
        *profile.relationships,
    ]
    values.extend(f"{name.replace('_', ' ').title()}: {value}" for name, value in profile.facts)
    return list(dict.fromkeys(values))


def expansion_terms(profile: LegalQueryProfile) -> list[str]:
    """Return conservative synonyms for lexical recall without query drift."""

    terms: list[str] = []
    for concept in profile.concepts:
        terms.extend(LEGAL_CONCEPTS.get(concept, ())[:3])
    for statute in profile.statutes:
        terms.extend(STATUTE_ALIASES.get(statute, ())[:2])
    terms.extend(profile.sections)
    return list(dict.fromkeys(term.lower() for term in terms if len(term) >= 3))
