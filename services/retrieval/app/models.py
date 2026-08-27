from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SearchFilters(BaseModel):
    court: str = "All Courts"
    year: str = "All Years"
    issue: str = "All Issues"
    outcome: str = "Any Outcome"

    @field_validator("court")
    @classmethod
    def validate_court(cls, value: str) -> str:
        allowed = {"All Courts", "Supreme Court", "High Court"}
        if value not in allowed:
            raise ValueError("Unsupported court filter")
        return value

    @field_validator("year")
    @classmethod
    def validate_year(cls, value: str) -> str:
        if value != "All Years" and (not value.isdigit() or not 1900 <= int(value) <= 2100):
            raise ValueError("Unsupported year filter")
        return value

    @field_validator("issue")
    @classmethod
    def validate_issue(cls, value: str) -> str:
        allowed = {
            "All Issues",
            "Regular Bail",
            "Anticipatory Bail",
            "Default Bail",
            "Prolonged Custody",
            "Documentary Evidence",
            "Witness Interference",
            "Flight Risk",
            "Criminal Law",
            "Constitutional Law",
            "Service Law",
            "Taxation",
            "Arbitration",
            "Property / Land",
            "Succession / Inheritance",
            "Probate / Wills",
            "Tenancy / Rent Control",
            "Family / Matrimonial",
            "Motor Vehicles / Compensation",
            "Consumer Law",
            "Insolvency",
            "Environmental Law",
            "Narcotics / NDPS",
            "Economic Offences / PMLA",
            "Cheque Dishonour",
            "Civil Procedure",
            "Quashing of Criminal Proceedings",
            "Unclassified",
        }
        if value not in allowed:
            raise ValueError("Unsupported legal-issue filter")
        return value

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, value: str) -> str:
        allowed = {
            "Any Outcome",
            "Petitioner / Appellant side succeeded",
            "Respondent / State side succeeded",
            "Partial / mixed relief",
            "Remanded / no final winner",
        }
        if value not in allowed:
            raise ValueError("Unsupported outcome filter")
        return value


class SearchRequest(BaseModel):
    query: str = Field(min_length=20, max_length=4000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=10, alias="topK", ge=1, le=20)

    model_config = {"populate_by_name": True}

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned.split()) < 4:
            raise ValueError("Describe at least four meaningful words")
        return cleaned


class EvidenceLocator(BaseModel):
    section: str
    paragraph: str


class SearchResult(BaseModel):
    id: str
    rank: int
    title: str
    court: str
    year: str
    category: str
    citation: str
    posture: str
    legalIssues: list[str]
    filterIssues: list[str]
    matchedEvidence: str
    caseSummary: str
    highlightPhrases: list[str]
    outcome: str
    matterStatus: str
    trialStatus: str
    winner: str
    caseStage: str
    caseStageConfidence: str
    caseStageEvidence: str
    outcomeRelief: str
    outcomeEvidence: str
    relevanceBasis: list[str]
    authorityScore: float
    authorityBasis: list[str]
    benchStrength: str
    whyItMatched: list[str]
    explanation: dict[str, object]
    sourceUrl: str
    evidenceLocator: EvidenceLocator
    reasonCodes: list[str]
    denseRank: int | None = None
    lexicalRank: int | None = None
    retrievalScore: float


class SearchResponse(BaseModel):
    runId: str
    corpusVersion: str
    modelVersion: str
    retrievalMethod: str
    extractedSignals: list[str]
    latencyMs: int
    caseCount: int
    chunkCount: int
    results: list[SearchResult]


class HealthResponse(BaseModel):
    status: Literal["ready", "starting"]
    corpusVersion: str
    modelVersion: str
    caseCount: int
    chunkCount: int


class GraphRequest(BaseModel):
    caseIds: list[str] = Field(min_length=1, max_length=20)


class GraphNode(BaseModel):
    id: str
    title: str
    citation: str
    court: str
    year: str
    category: str
    isResult: bool
    sourceUrl: str


class GraphEdge(BaseModel):
    source: str
    target: str
    type: Literal["cites", "statute"]
    label: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    citationEdgeCount: int
    statuteEdgeCount: int
