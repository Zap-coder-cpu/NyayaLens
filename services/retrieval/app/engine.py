from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterable
from urllib.parse import quote

import numpy as np
from fastembed import TextEmbedding

from .case_analysis import (
    VERIFY,
    build_case_summary,
    extract_case_stage,
    extract_disposition,
    infer_bench_strength,
)
from .legal_query import (
    LEGAL_CONCEPTS,
    LegalQueryProfile,
    analyze_legal_query,
    expansion_terms,
    profile_signals,
)
from .models import (
    EvidenceLocator,
    GraphEdge,
    GraphNode,
    GraphResponse,
    SearchFilters,
    SearchResponse,
    SearchResult,
)


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
SAMPLE_CORPUS_PATH = ROOT / "corpus" / "cases.json"
IMPORTED_CORPUS_PATH = ROOT / "data" / "import" / "cases.json"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "search.db"
MODEL_CACHE = DATA_DIR / "model-cache"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
RRF_K = 60
INDEX_SCHEMA_VERSION = "4"
VECTOR_SELECTOR_VERSION = "facts-decision-v3"
LEXICAL_SELECTOR_VERSION = "source-passages-v2"
try:
    INDEX_WORKERS = max(1, min(2, int(os.getenv("RETRIEVAL_INDEX_WORKERS", "1"))))
except ValueError:
    INDEX_WORKERS = 1


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: str
    rank: int
    score: float
    match_kind: str = ""


def extract_signals(text: str) -> list[str]:
    return profile_signals(analyze_legal_query(text))[:16]


def _compact_alnum(text: str) -> str:
    """Lowercase, alnum-only form used to match citation strings despite spacing/punctuation drift."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def lexical_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
        "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were",
        "with", "where", "which", "after", "before", "seeks", "applicant", "case",
    }
    return [token for token in tokens if len(token) > 2 and token not in stop]


LEGAL_DOMAIN_TERMS = {
    "accused", "act", "appeal", "appellant", "arbitration", "bail", "case", "citation",
    "constitution", "contract", "court", "crime", "criminal", "custody", "defendant",
    "detention", "divorce", "evidence", "fir", "injunction", "judgment", "law", "legal",
    "offence", "petition", "petitioner", "plaintiff", "prosecution", "property", "relief",
    "respondent", "section", "sentence", "statute", "tax", "tenant", "tribunal", "writ",
}


def is_legal_query(text: str) -> bool:
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    profile = analyze_legal_query(text)
    return bool(
        tokens & LEGAL_DOMAIN_TERMS
        or profile.concepts
        or profile.domains
        or profile.statutes
        or profile.sections
        or profile.reliefs
    )


class SemanticEngine:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        # Runtime search is deliberately offline: once the model has been installed,
        # service startup must never depend on a registry request or an API key.
        self._model = TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=str(MODEL_CACHE),
            threads=4,
            local_files_only=True,
        )
        self._corpus_path = IMPORTED_CORPUS_PATH if IMPORTED_CORPUS_PATH.exists() else SAMPLE_CORPUS_PATH
        self._corpus = self._load_corpus()
        self._cases = {case["id"]: case for case in self._corpus["cases"]}
        self._chunks = {
            chunk["id"]: {**chunk, "case_id": case["id"]}
            for case in self._corpus["cases"]
            for chunk in case["chunks"]
        }
        self._chunks_by_case: dict[str, list[str]] = defaultdict(list)
        self._chunk_positions: dict[str, int] = {}
        for chunk_id, chunk in self._chunks.items():
            case_id = chunk["case_id"]
            self._chunk_positions[chunk_id] = len(self._chunks_by_case[case_id])
            self._chunks_by_case[case_id].append(chunk_id)
        self._disposition_cache: dict[str, tuple[str, str, str, str, str, str]] = {}
        self._context_anchor_cache: dict[str, tuple[str, str, str]] = {}
        self._primary_profile_cache: dict[str, LegalQueryProfile] = {}
        self._case_issue_cache: dict[str, tuple[str, ...]] = {}
        self._cites_out: dict[str, set[str]] | None = None
        self._cited_by: dict[str, set[str]] | None = None
        self._ensure_index()
        self._load_vectors()

    @property
    def corpus_version(self) -> str:
        return str(self._corpus["corpusVersion"])

    @property
    def model_version(self) -> str:
        return MODEL_NAME

    @property
    def case_count(self) -> int:
        return len(self._cases)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        return connection

    def _load_corpus(self) -> dict[str, object]:
        return json.loads(self._corpus_path.read_text(encoding="utf-8"))

    def _corpus_hash(self) -> str:
        digest = hashlib.sha256()
        with self._corpus_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _chunk_index_text(case: dict[str, object], chunk: dict[str, object]) -> str:
        stored = chunk.get("indexText")
        if isinstance(stored, str):
            return stored
        # Whole-document issue labels are intentionally excluded: imported
        # judgments often quote many unrelated areas of law, and repeating all
        # labels in every FTS row turns incidental citations into lexical hits.
        # Newer corpora may attach passage-local structured fields, which are
        # safe to add because they describe this exact evidence passage.
        passage_metadata = " ".join(
            str(item)
            for field in ("legalDomains", "statutes", "sections", "reliefs", "postures")
            for item in chunk.get(field, [])
        )
        return " ".join(
            (
                str(case["title"]),
                str(case["citation"]),
                passage_metadata,
                str(chunk["evidence"]),
            )
        )[:4_000]

    def _passage_selector_scores(
        self,
        case_id: str,
        chunk_id: str,
        *,
        position: int | None = None,
        total: int | None = None,
    ) -> tuple[float, float, float]:
        """Return deterministic facts, decision and order scores for one passage.

        The imported corpus predates structured passage labels, so the selector
        deliberately works from the judgment text as well as any newer labels.
        Quotation/citation penalties stop a discussion of another decision from
        becoming the semantic representation of the current case.
        """

        chunk = self._chunks[chunk_id]
        text = re.sub(r"\s+", " ", str(chunk["evidence"]).lower())
        section = str(chunk.get("section", "")).lower()
        chunk_ids = self._chunks_by_case[case_id]
        if position is None:
            position = getattr(self, "_chunk_positions", {}).get(chunk_id)
        if position is None:
            position = chunk_ids.index(chunk_id)
        total = total or len(chunk_ids)
        progress = position / max(1, total - 1)

        header_hits = sum(
            marker in text[:800]
            for marker in ("appearance:", "present:-", "counsel for", "coram:", "case no.")
        )
        submission_hits = sum(
            marker in text
            for marker in (
                "learned counsel submitted", "learned counsel contended",
                "counsel for the appellant argued", "it was submitted on behalf",
                "the respondent contended", "according to the appellant",
            )
        )
        citation_hits = len(re.findall(r"\b(?:air|scc|scr|insc|scc on(?:line|l))\b", text))
        cited_case_hits = len(re.findall(r"\b(?:v\.?|vs\.?|versus)(?=\s)", text))
        quotation_hits = sum(
            marker in text
            for marker in (
                "held as follows", "observed as follows", "reads as follows",
                "in the case of", "relying upon the decision", "reported in",
                "the aforesaid decision", "in paragraph ", "quoted hereinbelow",
            )
        )
        current_voice_hits = sum(
            marker in text
            for marker in (
                "we hold", "we find", "we conclude", "we are of the view",
                "in our view", "this court is of the view", "we therefore",
                "we accordingly", "for the reasons stated above",
            )
        )
        fact_hits = sum(
            marker in text
            for marker in (
                "brief facts", "facts of the case", "factual background",
                "prosecution case", "material facts", "factual matrix",
                "died intestate", "legal heirs", "immovable property",
                "remained in custody", "investigation is complete",
                "charge sheet", "agreement to sell", "landlord", "tenant",
            )
        )
        legal_application_hits = sum(
            marker in text
            for marker in (
                "the question for consideration", "applying the", "in view of the above",
                "therefore", "accordingly", "we have considered", "we have found",
                "the legal position", "the issue is", "section ", "article ",
            )
        )
        order_hits = sum(
            marker in text
            for marker in (
                "appeal is allowed", "appeal is dismissed", "petition is allowed",
                "petition is dismissed", "application is allowed",
                "application is dismissed", "quashed and set aside",
                "stands disposed of", "disposed of accordingly", "matter is remanded",
                "released on bail", "enlarged on bail",
            )
        )

        citation_penalty = min(12.0, citation_hits * 1.1 + cited_case_hits * 1.4 + quotation_hits * 2.2)
        common_penalty = header_hits * 5.0 + submission_hits * 4.0 + citation_penalty
        facts_score = (
            fact_hits * 5.0
            + (2.0 if progress <= 0.45 else 0.0)
            + min(3.0, len(re.findall(r"\b\d+(?:\.\d+)?\b", text)) * 0.25)
            - common_penalty
            - order_hits * 1.5
        )
        decision_score = (
            current_voice_hits * 7.0
            + legal_application_hits * 1.4
            + (2.0 if progress >= 0.35 else 0.0)
            + order_hits * 1.5
            - common_penalty
        )
        order_score = order_hits * 8.0 + progress * 3.0 - header_hits * 4.0 - submission_hits * 2.0

        if section == "material facts":
            facts_score += 9.0
        elif section == "court reasoning":
            decision_score += 9.0
        elif section == "operative order":
            order_score += 12.0
            decision_score += 2.0
        elif section == "party submissions":
            facts_score -= 10.0
            decision_score -= 10.0
        elif section == "cited authorities":
            facts_score -= 14.0
            decision_score -= 14.0
        return facts_score, decision_score, order_score

    def _context_anchors_for_case(self, case_id: str) -> tuple[str, str, str]:
        if not hasattr(self, "_context_anchor_cache"):
            self._context_anchor_cache = {}
        cached = self._context_anchor_cache.get(case_id)
        if cached:
            return cached
        chunk_ids = self._chunks_by_case[case_id]
        total = len(chunk_ids)
        scores = {
            chunk_id: self._passage_selector_scores(
                case_id, chunk_id, position=position, total=total
            )
            for position, chunk_id in enumerate(chunk_ids)
        }
        facts_id = max(chunk_ids, key=lambda item: scores[item][0])
        decision_candidates = [item for item in chunk_ids if item != facts_id] or chunk_ids
        decision_id = max(decision_candidates, key=lambda item: scores[item][1])
        tail_ids = chunk_ids[-min(14, len(chunk_ids)) :]
        order_id = max(tail_ids, key=lambda item: scores[item][2])
        anchors = (facts_id, decision_id, order_id)
        self._context_anchor_cache[case_id] = anchors
        return anchors

    def _case_primary_profile(self, case_id: str) -> LegalQueryProfile:
        if not hasattr(self, "_primary_profile_cache"):
            self._primary_profile_cache = {}
        cached = self._primary_profile_cache.get(case_id)
        if cached:
            return cached
        facts_id, decision_id, order_id = self._context_anchors_for_case(case_id)
        primary_text = " ".join(
            str(self._chunks[item]["evidence"])
            for item in dict.fromkeys((facts_id, decision_id, order_id))
        )
        profile = analyze_legal_query(primary_text, infer_intent=False)
        self._primary_profile_cache[case_id] = profile
        return profile

    def _embedding_documents_for_case(
        self, case_id: str
    ) -> list[tuple[str, str, tuple[str, ...], str]]:
        """Create two complementary vectors: factual context and decision/holding."""

        case = self._cases[case_id]
        facts_id, decision_id, order_id = self._context_anchors_for_case(case_id)
        primary = self._case_primary_profile(case_id)

        def stored_values(field: str, fallback: tuple[str, ...]) -> list[str]:
            values = case.get(field, [])
            if isinstance(values, list) and values:
                return [str(item) for item in values]
            return list(fallback)

        domains = stored_values("controllingLegalDomains", primary.domains)
        statutes = stored_values("controllingStatutes", primary.statutes)
        sections = stored_values("controllingSections", primary.sections)
        reliefs = stored_values("controllingReliefs", primary.reliefs)
        relationships = stored_values("partyRelationships", primary.relationships)
        metadata = "; ".join(
            part
            for part in (
                "Primary legal domain: " + ", ".join(domains[:3]) if domains else "",
                "Controlling law: " + ", ".join(statutes[:3]) if statutes else "",
                "Provisions: " + ", ".join(sections[:4]) if sections else "",
                "Relief: " + ", ".join(reliefs[:3]) if reliefs else "",
                "Party relationship: " + ", ".join(relationships[:2]) if relationships else "",
            )
            if part
        )
        facts_text = str(self._chunks[facts_id]["evidence"])
        decision_text = str(self._chunks[decision_id]["evidence"])
        order_text = str(self._chunks[order_id]["evidence"])
        facts_document = f"{metadata}\nMaterial factual context and relief: {facts_text[:1_350]}"[:1_750]
        decision_document = (
            f"{metadata}\nCourt's reasoning and holding: {decision_text[:1_150]}"
            f"\nOperative result: {order_text[:300]}"
        )[:1_750]
        return [
            ("facts", facts_id, (facts_id,), facts_document),
            (
                "decision",
                decision_id,
                tuple(dict.fromkeys((decision_id, order_id))),
                decision_document,
            ),
        ]

    def _embedding_text_for_case(self, case_id: str) -> tuple[str, str]:
        """Backward-compatible access to the decision representation."""

        decision = self._embedding_documents_for_case(case_id)[1]
        return decision[1], decision[3]

    def _ensure_index(self) -> None:
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    index_text TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    case_id UNINDEXED,
                    index_text,
                    tokenize='porter unicode61'
                );
                """
            )
            embedding_columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(case_embeddings)").fetchall()
            }
            required_embedding_columns = {
                "embedding_id", "case_id", "representative_chunk_id",
                "embedding_kind", "source_chunk_ids_json", "embedding",
            }
            if embedding_columns != required_embedding_columns:
                db.execute("DROP TABLE IF EXISTS case_embeddings")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS case_embeddings (
                    embedding_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    representative_chunk_id TEXT NOT NULL,
                    embedding_kind TEXT NOT NULL,
                    source_chunk_ids_json TEXT NOT NULL,
                    embedding BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_case_embeddings_case_id
                    ON case_embeddings(case_id);
                """
            )
            schema = db.execute("SELECT value FROM index_meta WHERE key='schema_version'").fetchone()
            current = db.execute("SELECT value FROM index_meta WHERE key='corpus_hash'").fetchone()
            model = db.execute("SELECT value FROM index_meta WHERE key='model_version'").fetchone()
            selector = db.execute(
                "SELECT value FROM index_meta WHERE key='vector_selector_version'"
            ).fetchone()
            lexical_selector = db.execute(
                "SELECT value FROM index_meta WHERE key='lexical_selector_version'"
            ).fetchone()
            corpus_hash = self._corpus_hash()
            indexed_chunks = int(db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
            indexed_fts_chunks = int(
                db.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
            )
            indexed_vectors = int(
                db.execute("SELECT COUNT(*) FROM case_embeddings").fetchone()[0]
            )
            corpus_matches = bool(current and current["value"] == corpus_hash)
            needs_lexical_rebuild = bool(
                not corpus_matches
                or indexed_chunks != len(self._chunks)
                or indexed_fts_chunks != len(self._chunks)
                or not lexical_selector
                or lexical_selector["value"] != LEXICAL_SELECTOR_VERSION
            )
            needs_vector_rebuild = bool(
                not corpus_matches
                or not model
                or model["value"] != MODEL_NAME
                or not schema
                or schema["value"] != INDEX_SCHEMA_VERSION
                or not selector
                or selector["value"] != VECTOR_SELECTOR_VERSION
                or indexed_vectors != len(self._cases) * 2
            )
            if not needs_lexical_rebuild and not needs_vector_rebuild:
                return

            if needs_lexical_rebuild:
                db.execute("DELETE FROM chunks")
                db.execute("DELETE FROM chunks_fts")
                chunk_items = list(self._chunks.items())
                print(f"Building lexical index for {len(chunk_items):,} passages...", flush=True)
                lexical_batch_size = 5_000
                for start in range(0, len(chunk_items), lexical_batch_size):
                    batch = chunk_items[start : start + lexical_batch_size]
                    rows = [
                        (
                            chunk_id,
                            str(chunk["case_id"]),
                            self._chunk_index_text(self._cases[chunk["case_id"]], chunk),
                        )
                        for chunk_id, chunk in batch
                    ]
                    db.executemany(
                        "INSERT INTO chunks(chunk_id, case_id, index_text) VALUES (?, ?, ?)",
                        rows,
                    )
                    db.executemany(
                        "INSERT INTO chunks_fts(chunk_id, case_id, index_text) VALUES (?, ?, ?)",
                        rows,
                    )
                    if start == 0 or start + len(batch) == len(chunk_items) or (start // lexical_batch_size + 1) % 5 == 0:
                        print(
                            f"Indexed {start + len(batch):,}/{len(chunk_items):,} passages",
                            flush=True,
                        )

            if needs_vector_rebuild:
                db.execute("DELETE FROM case_embeddings")
                case_items = list(self._cases.items())
                print(
                    f"Building two-vector semantic index for {len(case_items):,} judgments...",
                    flush=True,
                )
                case_batch_size = 256
                for start in range(0, len(case_items), case_batch_size):
                    batch = case_items[start : start + case_batch_size]
                    records: list[tuple[str, str, str, tuple[str, ...], str]] = []
                    for case_id, _ in batch:
                        for kind, representative_id, source_ids, dense_text in self._embedding_documents_for_case(case_id):
                            records.append((case_id, kind, representative_id, source_ids, dense_text))
                    embeddings = list(
                        self._model.embed(
                            # Default to one low-memory process. Developers with
                            # ample RAM may set RETRIEVAL_INDEX_WORKERS=2 for a
                            # faster rebuild; this never changes vector values.
                            [record[4] for record in records],
                            batch_size=64,
                            parallel=INDEX_WORKERS if INDEX_WORKERS > 1 else None,
                        )
                    )
                    if len(embeddings) != len(records):
                        raise RuntimeError("Embedding model returned an unexpected vector count")
                    for record, vector in zip(records, embeddings, strict=True):
                        case_id, kind, representative_id, source_ids, _ = record
                        normalized = self._normalize(np.asarray(vector, dtype=np.float32))
                        db.execute(
                            """
                            INSERT INTO case_embeddings(
                                embedding_id, case_id, representative_chunk_id,
                                embedding_kind, source_chunk_ids_json, embedding
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{case_id}:{kind}", case_id, representative_id, kind,
                                json.dumps(source_ids), normalized.tobytes(),
                            ),
                        )
                    if (
                        start == 0
                        or start + len(batch) == len(case_items)
                        or (start // case_batch_size + 1) % 2 == 0
                    ):
                        print(
                            f"Embedded {start + len(batch):,}/{len(case_items):,} judgments "
                            f"({(start + len(batch)) * 2:,} vectors)",
                            flush=True,
                        )
            db.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('corpus_hash', ?)",
                (corpus_hash,),
            )
            db.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('model_version', ?)",
                (MODEL_NAME,),
            )
            db.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('schema_version', ?)",
                (INDEX_SCHEMA_VERSION,),
            )
            db.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('vector_selector_version', ?)",
                (VECTOR_SELECTOR_VERSION,),
            )
            db.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('lexical_selector_version', ?)",
                (LEXICAL_SELECTOR_VERSION,),
            )

    def _load_vectors(self) -> None:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT case_id, representative_chunk_id, embedding_kind,
                       source_chunk_ids_json, embedding
                FROM case_embeddings
                ORDER BY case_id, embedding_kind
                """
            ).fetchall()
        self._vector_case_ids = [row["case_id"] for row in rows]
        self._representative_chunk_ids = [row["representative_chunk_id"] for row in rows]
        self._vector_kinds = [row["embedding_kind"] for row in rows]
        self._vector_source_chunk_ids = [
            tuple(json.loads(row["source_chunk_ids_json"])) for row in rows
        ]
        self._vectors = np.stack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])
        loaded_anchors: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = defaultdict(dict)
        for case_id, representative_id, kind, source_ids in zip(
            self._vector_case_ids,
            self._representative_chunk_ids,
            self._vector_kinds,
            self._vector_source_chunk_ids,
            strict=True,
        ):
            loaded_anchors[case_id][kind] = (representative_id, source_ids)
        for case_id, anchors in loaded_anchors.items():
            if "facts" not in anchors or "decision" not in anchors:
                continue
            facts_id = anchors["facts"][0]
            decision_id, decision_sources = anchors["decision"]
            order_id = decision_sources[-1] if decision_sources else decision_id
            self._context_anchor_cache[case_id] = (facts_id, decision_id, order_id)

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        return vector if math.isclose(norm, 0.0) else vector / norm

    def _case_allowed(self, case_id: str, filters: SearchFilters) -> bool:
        case = self._cases[case_id]
        if filters.court != "All Courts" and case["court"] != filters.court:
            return False
        if filters.year != "All Years" and str(case["year"]) != filters.year:
            return False
        if filters.issue != "All Issues" and filters.issue not in self._case_issue_labels(case_id):
            return False
        return True

    def _case_issue_labels(self, case_id: str) -> tuple[str, ...]:
        """Return substantive issue labels even for older imported manifests.

        The first imported corpus stored broad whole-document labels, which can
        omit the judgment's actual subject (or include law found only in cited
        authorities).  Runtime facts/decision anchors provide a safer fallback
        for both advanced-search filtering and the result-card labels.
        """

        cached = self._case_issue_cache.get(case_id)
        if cached is not None:
            return cached
        case = self._cases[case_id]
        primary = self._case_primary_profile(case_id)
        candidates = [
            *(str(item) for item in (case.get("controllingLegalDomains") or [])),
            *primary.domains,
            *primary.concepts,
            *(str(item) for item in (case.get("legalIssues") or [])),
        ]
        labels = tuple(dict.fromkeys(item for item in candidates if item and item != "Unclassified"))
        if not labels:
            labels = ("Unclassified",)
        self._case_issue_cache[case_id] = labels
        return labels

    def _dense(self, query: str, filters: SearchFilters, limit: int = 100) -> list[RankedChunk]:
        with self._lock:
            query_vector = next(iter(self._model.query_embed(query)))
        normalized = self._normalize(np.asarray(query_vector, dtype=np.float32))
        similarities = self._vectors @ normalized
        ordered = np.argsort(-similarities)
        results: list[RankedChunk] = []
        seen_cases: set[str] = set()
        for index in ordered:
            case_id = self._vector_case_ids[int(index)]
            # A judgment has a facts vector and a decision vector.  Only its
            # strongest vector contributes a dense rank/RRF vote, avoiding a
            # long-document or duplicate-vector advantage.
            if case_id in seen_cases:
                continue
            if self._case_allowed(case_id, filters):
                seen_cases.add(case_id)
                chunk_id = self._representative_chunk_ids[int(index)]
                results.append(
                    RankedChunk(
                        chunk_id=chunk_id,
                        rank=len(results) + 1,
                        score=float(similarities[int(index)]),
                        match_kind=self._vector_kinds[int(index)],
                    )
                )
            if len(results) >= limit:
                break
        return results

    def _best_chunk_for_case(self, case_id: str, query: str) -> str:
        profile = analyze_legal_query(query)
        query_tokens = list(dict.fromkeys(lexical_tokens(query)))
        expanded_phrases = expansion_terms(profile)
        return max(
            self._chunks_by_case[case_id],
            key=lambda chunk_id: self._passage_relevance_score(
                chunk_id,
                query,
                profile,
                query_tokens=query_tokens,
                expanded_phrases=expanded_phrases,
            ),
        )

    def _passage_relevance_score(
        self,
        chunk_id: str,
        query: str,
        profile: LegalQueryProfile,
        *,
        query_tokens: list[str] | None = None,
        expanded_phrases: list[str] | None = None,
    ) -> float:
        chunk = self._chunks[chunk_id]
        haystack = self._chunk_index_text(
            self._cases[str(chunk["case_id"])], chunk
        ).lower()
        query_tokens = query_tokens or list(dict.fromkeys(lexical_tokens(query)))
        expanded_phrases = expanded_phrases or expansion_terms(profile)
        haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        score = sum(2.0 for token in query_tokens if token in haystack_tokens)
        score += sum(min(4, haystack.count(token)) * 0.4 for token in query_tokens)

        for phrase in expanded_phrases:
            if " " in phrase and phrase in haystack:
                score += 4.0
        for statute in profile.statutes:
            aliases = lexical_tokens(statute)
            if aliases and all(token in haystack_tokens for token in aliases[:3]):
                score += 7.0
        for section in profile.sections:
            compact = section.lower().replace("section ", "")
            if section.lower() in haystack or compact in haystack:
                score += 6.0
        case_id = str(self._chunks[chunk_id]["case_id"])
        role_adjustment, role_reason = self._passage_role_adjustment(case_id, chunk_id, profile)
        if "cited authorities" in role_reason:
            role_factor = 0.30
        elif "party submission" in role_reason:
            role_factor = 0.55
        elif "case-header" in role_reason:
            role_factor = 0.35
        elif "current court's reasoning" in role_reason:
            role_factor = 1.15
        elif "material facts" in role_reason:
            role_factor = 1.12
        elif "operative order" in role_reason:
            role_factor = 1.10 if profile.reliefs or profile.postures else 0.90
        else:
            role_factor = 1.0
        return score * role_factor + role_adjustment * 40

    def _lexical(self, query: str, filters: SearchFilters, limit: int = 100) -> list[RankedChunk]:
        # Keep the primary BM25 branch faithful to the user's actual words.
        # Synonyms are applied in passage selection/reranking; adding all of them
        # to one OR query diluted exact statute and provision matches.
        tokens = list(dict.fromkeys(lexical_tokens(query)))
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:45])
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT chunk_id, case_id, bm25(chunks_fts) AS score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY score ASC
                LIMIT ?
                """,
                (fts_query, max(limit * 20, 2_000)),
            ).fetchall()
        profile = analyze_legal_query(query)
        expanded_phrases = expansion_terms(profile)
        best_by_case: dict[str, tuple[float, sqlite3.Row]] = {}
        for row in rows:
            case_id = row["case_id"]
            if not self._case_allowed(case_id, filters):
                continue
            raw_relevance = max(0.0, -float(row["score"]))
            passage_relevance = self._passage_relevance_score(
                row["chunk_id"],
                query,
                profile,
                query_tokens=tokens,
                expanded_phrases=expanded_phrases,
            )
            combined = raw_relevance + passage_relevance * 0.35
            current = best_by_case.get(case_id)
            if current is None or combined > current[0]:
                best_by_case[case_id] = (combined, row)

        ordered_cases = sorted(
            best_by_case.items(), key=lambda item: (-item[1][0], item[0])
        )[:limit]
        results: list[RankedChunk] = []
        for rank, (_, (combined, row)) in enumerate(ordered_cases, start=1):
            results.append(
                RankedChunk(
                    chunk_id=row["chunk_id"],
                    rank=rank,
                    score=combined,
                    match_kind="lexical",
                )
            )
        return results

    @staticmethod
    def _rank_map(items: Iterable[RankedChunk]) -> dict[str, int]:
        return {item.chunk_id: item.rank for item in items}

    def _case_full_text(self, case_id: str) -> str:
        return " ".join(
            str(self._chunks[chunk_id]["evidence"])
            for chunk_id in self._chunks_by_case[case_id]
        )

    def _case_disposition(self, case_id: str) -> tuple[str, str, str, str, str, str]:
        cached = self._disposition_cache.get(case_id)
        if cached:
            return cached
        case = self._cases[case_id]
        stored_fields = (
            "matterStatus", "trialStatus", "winner", "caseOutcome",
            "outcomeRelief", "outcomeEvidence",
        )
        if all(case.get(field) for field in stored_fields):
            values = tuple(str(case[field]) for field in stored_fields)
        else:
            conclusion_text = " ".join(
                str(self._chunks[chunk_id]["evidence"])
                for chunk_id in self._chunks_by_case[case_id][-8:]
            )
            disposition = extract_disposition(conclusion_text)
            values = (
                disposition.matter_status,
                disposition.trial_status,
                disposition.winner,
                disposition.case_outcome,
                disposition.outcome_relief,
                disposition.evidence,
            )
        self._disposition_cache[case_id] = values  # type: ignore[assignment]
        return values  # type: ignore[return-value]

    @staticmethod
    def _matches_outcome_filter(selected: str, winner: str, matter_status: str) -> bool:
        if selected == "Any Outcome":
            return True
        lowered = winner.lower()
        if selected == "Petitioner / Appellant side succeeded":
            return any(role in lowered for role in ("petitioner", "appellant", "applicant", "accused"))
        if selected == "Respondent / State side succeeded":
            return "respondent" in lowered or "state" in lowered
        if selected == "Partial / mixed relief":
            return "mixed" in lowered or "partial" in lowered
        if selected == "Remanded / no final winner":
            return "remand" in lowered or "remand" in matter_status.lower() or "no final winner" in lowered
        return False

    def _passage_role_adjustment(
        self,
        case_id: str,
        chunk_id: str,
        query_profile: LegalQueryProfile,
    ) -> tuple[float, str]:
        """Prefer the current court's facts/reasoning over incidental quotations."""

        chunk = self._chunks[chunk_id]
        text = str(chunk["evidence"]).lower()
        section = str(chunk.get("section", "")).lower()
        chunk_ids = self._chunks_by_case[case_id]
        position = getattr(self, "_chunk_positions", {}).get(chunk_id)
        if position is None:
            position = chunk_ids.index(chunk_id)
        near_end = position >= max(0, len(chunk_ids) - 5)

        holding_markers = (
            "we hold", "we find", "we conclude", "we are of the view", "in our view",
            "this court holds", "accordingly, we", "for the reasons stated above",
        )
        order_markers = (
            "appeal is allowed", "appeal is dismissed", "petition is allowed",
            "petition is dismissed", "application is allowed", "application is dismissed",
            "quashed and set aside", "stands disposed of", "matter is remanded",
        )
        fact_markers = (
            "brief facts", "facts of the case", "factual background", "prosecution case",
            "case of the plaintiff", "case of the petitioner", "material facts",
        )
        submission_markers = (
            "learned counsel submitted", "learned counsel contended", "counsel for the appellant argued",
            "it was submitted on behalf", "the respondent contended",
        )
        adoption_markers = (
            "we agree", "we approve", "we respectfully agree", "the principle applies",
            "has been correctly held", "we apply", "we follow",
        )
        current_case_markers = (
            "in the present case", "in the instant case", "case at hand",
            "we have considered", "we have examined", "for the above reasons",
            "for the foregoing reasons",
        )

        citation_density = len(re.findall(r"\b(?:air|scc|scr|insc|scc on(?:line|l))\b", text))
        cited_case_density = len(re.findall(r"\b(?:v\.?|vs\.?|versus)(?=\s)", text))
        authority_leadin = bool(
            re.search(
                r"\b(?:in the case of|reliance (?:was |is )?placed on|relying (?:on|upon)|"
                r"reference may be made to|reported in|held as follows|observed as follows|"
                r"reads as follows|quoted hereinbelow)\b",
                text,
            )
        )

        if section == "operative order" or (near_end and any(marker in text for marker in order_markers)):
            adjustment = 0.003 if query_profile.reliefs or query_profile.postures else 0.0015
            return adjustment, "Matched passage is the current court's operative order"
        if section == "party submissions":
            return -0.003, "Matched passage is primarily a party submission"
        if (
            section == "cited authorities"
            or (citation_density >= 2 and cited_case_density >= 1)
            or (authority_leadin and cited_case_density >= 1)
        ) and section != "court reasoning" and not any(
            marker in text for marker in (*adoption_markers, *current_case_markers)
        ):
            return -0.004, "Matched passage mainly discusses cited authorities"
        if section == "court reasoning" or any(marker in text for marker in holding_markers):
            return 0.004, "Matched passage contains the current court's reasoning"
        if section == "material facts" or any(marker in text for marker in fact_markers):
            return 0.003, "Matched passage contains material facts"
        if any(marker in text for marker in submission_markers):
            return -0.003, "Matched passage is primarily a party submission"

        header_markers = sum(
            marker in text[:700]
            for marker in ("appearance:", "present:-", "counsel for", "coram:", "case no.")
        )
        if position == 0 and header_markers >= 3 and len(text) < 1_100:
            return -0.005, "Matched passage is mainly case-header material"
        return 0.0, "Matched passage has neutral contextual role"

    def _legal_relevance_adjustment(
        self,
        case_id: str,
        chunk_id: str,
        query: str,
        query_profile: LegalQueryProfile,
    ) -> tuple[float, list[str], int, int]:
        """Score substantive legal alignment separately from authority.

        Values are deliberately on the same small scale as RRF. Exact statutes,
        provisions and contradictions can therefore correct a vague dual-branch
        match, while authority remains only a tie-breaker.
        """

        case = self._cases[case_id]
        chunk_ids = self._chunks_by_case[case_id]
        position = getattr(self, "_chunk_positions", {}).get(chunk_id)
        if position is None:
            position = chunk_ids.index(chunk_id)
        context_ids = chunk_ids[max(0, position - 1) : min(len(chunk_ids), position + 2)]
        candidate_text = " ".join(
            (
                str(case["title"]),
                str(case["citation"]),
                *(
                    str(self._chunks[candidate_id]["evidence"])
                    for candidate_id in context_ids
                ),
            )
        )
        candidate_profile = analyze_legal_query(candidate_text, infer_intent=False)
        selected_passage_profile = analyze_legal_query(
            str(self._chunks[chunk_id]["evidence"]), infer_intent=False
        )
        primary_profile = self._case_primary_profile(case_id)
        score = 0.0
        reasons: list[str] = []
        core_matches = 0
        contradictions = 0

        stored_statutes = {
            str(item) for item in case.get("controllingStatutes", [])
        }
        central_statutes = set(primary_profile.statutes) | stored_statutes
        mentioned_statutes = {
            str(item) for item in case.get("statutes", [])
        } | set(candidate_profile.statutes)
        shared_central_statutes = sorted(set(query_profile.statutes) & central_statutes)
        shared_passage_statutes = sorted(
            (set(query_profile.statutes) & mentioned_statutes)
            - set(shared_central_statutes)
        )
        if shared_central_statutes:
            score += min(0.010, len(shared_central_statutes) * 0.007)
            core_matches += len(shared_central_statutes)
            reasons.append("Same controlling statute: " + ", ".join(shared_central_statutes[:2]))
        if shared_passage_statutes:
            score += min(0.002, len(shared_passage_statutes) * 0.001)
            reasons.append(
                "Statute mentioned incidentally: " + ", ".join(shared_passage_statutes[:2])
            )

        stored_sections = {
            str(item) for item in case.get("controllingSections", [])
        }
        central_sections = set(primary_profile.sections) | stored_sections
        mentioned_sections = {
            str(item) for item in case.get("sections", [])
        } | set(candidate_profile.sections)
        shared_central_sections = sorted(set(query_profile.sections) & central_sections)
        shared_passage_sections = sorted(
            (set(query_profile.sections) & mentioned_sections)
            - set(shared_central_sections)
        )
        if shared_central_sections:
            score += min(0.009, len(shared_central_sections) * 0.006)
            core_matches += len(shared_central_sections)
            reasons.append("Same controlling provision: " + ", ".join(shared_central_sections[:2]))
        if shared_passage_sections:
            score += min(0.002, len(shared_passage_sections) * 0.001)
            reasons.append(
                "Provision mentioned incidentally: " + ", ".join(shared_passage_sections[:2])
            )

        central_pairs = set(primary_profile.provision_pairs)
        central_pairs.update(
            (str(item.get("statute", "")), str(item.get("section", "")))
            for item in case.get("controllingProvisionPairs", [])
            if isinstance(item, dict)
        )
        shared_pairs = sorted(set(query_profile.provision_pairs) & central_pairs)
        if shared_pairs:
            score += min(0.010, len(shared_pairs) * 0.007)
            core_matches += len(shared_pairs)
            reasons.append(
                "Same Act–provision pair: "
                + ", ".join(f"{section} of {statute}" for statute, section in shared_pairs[:2])
            )
        elif query_profile.provision_pairs and shared_central_sections:
            query_pair_statutes = {statute for statute, _ in query_profile.provision_pairs}
            candidate_pair_statutes = {statute for statute, _ in central_pairs}
            if candidate_pair_statutes and not (query_pair_statutes & candidate_pair_statutes):
                score -= 0.008
                contradictions += 1
                reasons.append("Same section number appears under a different statute")

        stored_domains = {
            str(item) for item in case.get("controllingLegalDomains", [])
        }
        primary_domains = set(primary_profile.domains) | stored_domains
        shared_primary_domains = sorted(set(query_profile.domains) & primary_domains)
        mentioned_domains = set(candidate_profile.domains) - primary_domains
        shared_mentioned_domains = sorted(set(query_profile.domains) & mentioned_domains)
        if shared_primary_domains:
            score += min(0.007, len(shared_primary_domains) * 0.005)
            core_matches += 1
            reasons.append(
                "Current proceeding has the same domain: "
                + ", ".join(shared_primary_domains[:2])
            )
        elif query_profile.domains and primary_domains:
            score -= 0.012
            contradictions += 1
            reasons.append("Current proceeding has different legal-domain indicators")
        if shared_mentioned_domains:
            score += min(0.002, len(shared_mentioned_domains) * 0.001)
            reasons.append(
                "Query domain appears only incidentally in the matched discussion: "
                + ", ".join(shared_mentioned_domains[:2])
            )

        primary_concepts = set(primary_profile.concepts)
        shared_primary_concepts = sorted(set(query_profile.concepts) & primary_concepts)
        mentioned_concepts = set(candidate_profile.concepts) - primary_concepts
        shared_mentioned_concepts = sorted(set(query_profile.concepts) & mentioned_concepts)
        if shared_primary_concepts:
            score += min(0.010, len(shared_primary_concepts) * 0.004)
            core_matches += 1
            reasons.append("Same central legal issue: " + ", ".join(shared_primary_concepts[:3]))
        if shared_mentioned_concepts:
            score += min(0.002, len(shared_mentioned_concepts) * 0.001)
            reasons.append(
                "Legal issue appears only incidentally: "
                + ", ".join(shared_mentioned_concepts[:3])
            )

        stored_reliefs = {
            str(item) for item in case.get("controllingReliefs", [])
        }
        primary_reliefs = set(primary_profile.reliefs) | stored_reliefs
        shared_primary_reliefs = sorted(set(query_profile.reliefs) & primary_reliefs)
        shared_mentioned_reliefs = sorted(
            (set(query_profile.reliefs) & set(candidate_profile.reliefs)) - primary_reliefs
        )
        if shared_primary_reliefs:
            score += min(0.006, len(shared_primary_reliefs) * 0.004)
            core_matches += 1
            reasons.append("Same requested relief: " + ", ".join(shared_primary_reliefs[:2]))
        elif shared_mentioned_reliefs:
            score -= 0.012
            reasons.append(
                "Requested relief appears incidental to the current proceeding: "
                + ", ".join(shared_mentioned_reliefs[:2])
            )

        stored_postures = {
            str(item) for item in case.get("controllingPostures", [])
        }
        primary_postures = set(primary_profile.postures) | stored_postures
        shared_postures = sorted(set(query_profile.postures) & primary_postures)
        if shared_postures:
            score += min(0.006, len(shared_postures) * 0.004)
            reasons.append("Same procedural posture: " + ", ".join(shared_postures[:2]))

        primary_relationships = set(primary_profile.relationships)
        shared_relationships = sorted(
            set(query_profile.relationships) & primary_relationships
        )
        if shared_relationships:
            score += min(0.003, len(shared_relationships) * 0.0015)
            reasons.append("Same party relationship: " + ", ".join(shared_relationships[:2]))

        passage_adjustment, passage_reason = self._passage_role_adjustment(
            case_id, chunk_id, query_profile
        )
        query_facts = dict(query_profile.facts)
        candidate_facts = dict(primary_profile.facts)
        for item in case.get("controllingMaterialFacts", []):
            if isinstance(item, dict) and item.get("name") and item.get("value"):
                candidate_facts[str(item["name"])] = str(item["value"])
        if passage_adjustment >= 0:
            for name, value in selected_passage_profile.facts:
                candidate_facts.setdefault(name, value)
        matched_fact_count = 0
        for name, expected in query_facts.items():
            observed = candidate_facts.get(name)
            if observed is None:
                continue
            label = name.replace("_", " ")
            if observed == expected:
                score += 0.004
                matched_fact_count += 1
                reasons.append(f"Matching fact: {label} is {expected}")
            else:
                high_impact = {
                    "personal_law", "succession_mode", "property_character", "will_status",
                }
                score -= 0.030 if name in high_impact else 0.020
                contradictions += 1
                reasons.append(
                    f"Contradictory fact: requested {label}={expected}, passage indicates {observed}"
                )

        if len(query_facts) >= 3:
            fact_coverage = matched_fact_count / len(query_facts)
            if matched_fact_count == 0:
                score -= 0.012
                reasons.append("No confirmed match for the query's structured material facts")
            elif fact_coverage >= 0.75:
                score += 0.010
                reasons.append(f"High structured-fact coverage ({fact_coverage:.0%})")
            elif fact_coverage >= 0.50:
                score += 0.006
                reasons.append(f"Material structured-fact coverage ({fact_coverage:.0%})")

        query_tokens = set(lexical_tokens(query))
        facts_id, decision_id, _ = self._context_anchors_for_case(case_id)
        primary_text = " ".join(
            str(self._chunks[item]["evidence"])
            for item in dict.fromkeys((facts_id, decision_id, chunk_id))
            if item == chunk_id or self._passage_role_adjustment(case_id, item, query_profile)[0] >= 0
        )
        candidate_tokens = set(lexical_tokens(primary_text))
        if query_tokens:
            coverage = len(query_tokens & candidate_tokens) / len(query_tokens)
            score += min(0.006, coverage * 0.009)
            if coverage >= 0.45:
                reasons.append(f"Strong material-fact term coverage ({coverage:.0%})")

        normalized_candidate = re.sub(r"[^a-z0-9]+", " ", primary_text.lower()).strip()
        matched_phrases = [
            phrase for phrase in query_profile.material_phrases if phrase in normalized_candidate
        ]
        if matched_phrases:
            score += min(8, len(matched_phrases)) * 0.001
            reasons.append("Matching factual phrases: " + ", ".join(matched_phrases[:3]))

        shared_quantities = sorted(set(query_profile.quantities) & set(primary_profile.quantities))
        if shared_quantities:
            score += min(3, len(shared_quantities)) * 0.003
            reasons.append("Matching quantities/durations: " + ", ".join(shared_quantities[:3]))

        score += passage_adjustment
        if passage_adjustment:
            reasons.append(passage_reason)

        normalized_query = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        citation = str(case["citation"]).lower().strip()
        title = re.sub(r"[^a-z0-9]+", " ", str(case["title"]).lower()).strip()
        if citation and not citation.startswith("citation not extracted") and citation in query.lower():
            score += 0.025
            core_matches += 2
            reasons.append("Exact citation match")
        elif title and len(title) >= 12 and title in normalized_query:
            score += 0.020
            core_matches += 2
            reasons.append("Exact case-title match")

        return round(score, 6), reasons, core_matches, contradictions

    def _authority_adjustment(
        self,
        case_id: str,
        chunk_id: str,
        query: str,
        query_signals: list[str],
    ) -> tuple[float, list[str], str]:
        """Return a small transparent reranking adjustment, never a confidence score."""

        case = self._cases[case_id]
        basis: list[str] = []
        adjustment = 0.0
        court_name = str(case.get("courtName", case["court"]))
        query_lower = query.lower()

        if case["court"] == "Supreme Court":
            adjustment += 0.0008
            basis.append("Supreme Court authority")
        elif case["court"] == "High Court":
            court_alias = re.sub(r"(?i)\s+high court.*$", "", court_name).strip().lower()
            if court_name.lower() in query_lower or (len(court_alias) >= 5 and court_alias in query_lower):
                adjustment += 0.0007
                basis.append(f"Same named High Court: {court_name}")

        bench_text = " ".join(
            str(self._chunks[candidate_id]["evidence"])
            for candidate_id in self._chunks_by_case[case_id][:3]
        )
        if case.get("benchSize") is not None:
            bench_size = int(case.get("benchSize", 0))
            bench_label = str(case.get("benchStrength", "Bench size not extracted"))
        else:
            bench = infer_bench_strength(bench_text)
            bench_size = bench.size
            bench_label = bench.label
        if bench_size >= 5:
            adjustment += 0.0005
            basis.append(f"Larger binding bench: {bench_label}")
        elif bench_size >= 3:
            adjustment += 0.00035
            basis.append(f"Larger bench: {bench_label}")
        elif bench_size == 2:
            adjustment += 0.0002
            basis.append("Division bench")

        year = int(case.get("year", 0) or 0)
        if year:
            adjustment += max(0.0, min(0.00025, (year - 2000) / 26 * 0.00025))
            if year >= 2023:
                basis.append(f"Recent authority ({year})")

        case_issues = {issue.lower() for issue in self._case_issue_labels(case_id)}
        shared_issues = [signal for signal in query_signals if signal.lower() in case_issues]
        if shared_issues:
            adjustment += min(3, len(shared_issues)) * 0.00015
            basis.append("Same procedural/legal issue: " + ", ".join(shared_issues[:3]))

        query_sections = [signal for signal in query_signals if signal.startswith("Section ")]
        chunk_text = str(self._chunks[chunk_id]["evidence"]).lower()
        shared_sections = [section for section in query_sections if section.lower() in chunk_text]
        if shared_sections:
            adjustment += min(2, len(shared_sections)) * 0.00015
            basis.append("Same statutory provision: " + ", ".join(shared_sections[:2]))

        if not basis:
            basis.append("No additional hierarchy boost; ranked on retrieval relevance")
        return round(adjustment, 6), basis, bench_label

    def search(self, query: str, filters: SearchFilters, top_k: int) -> SearchResponse:
        started = time.perf_counter()
        if not is_legal_query(query):
            return SearchResponse(
                runId=str(uuid.uuid4()),
                corpusVersion=self.corpus_version,
                modelVersion=self.model_version,
                retrievalMethod=f"Dense cosine + SQLite FTS5 + RRF(k={RRF_K}) + authority reranking",
                extractedSignals=[],
                latencyMs=round((time.perf_counter() - started) * 1000),
                caseCount=self.case_count,
                chunkCount=self.chunk_count,
                results=[],
            )
        query_profile = analyze_legal_query(query)
        candidate_limit = 300 if filters.outcome != "Any Outcome" else 150
        dense = self._dense(query, filters, limit=candidate_limit)
        lexical = self._lexical(query, filters, limit=candidate_limit)
        query_signals = profile_signals(query_profile)[:16]

        # Do not manufacture plausible-looking legal results for an unrelated query.
        # Dense-only matches are allowed when the input contains a recognised legal
        # signal; otherwise at least one corpus term must also match.
        if not lexical and not query_signals and (not dense or dense[0].score < 0.48):
            return SearchResponse(
                runId=str(uuid.uuid4()),
                corpusVersion=self.corpus_version,
                modelVersion=self.model_version,
                retrievalMethod=f"Dense cosine + SQLite FTS5 + RRF(k={RRF_K}) + authority reranking",
                extractedSignals=[],
                latencyMs=round((time.perf_counter() - started) * 1000),
                caseCount=self.case_count,
                chunkCount=self.chunk_count,
                results=[],
            )

        # Fuse at judgment level. Dense and lexical retrieval often identify
        # different relevant passages in the same judgment; passage-ID fusion
        # incorrectly discarded that agreement and favoured long documents.
        dense_by_case = {
            self._chunks[item.chunk_id]["case_id"]: item for item in dense
        }
        lexical_by_case = {
            self._chunks[item.chunk_id]["case_id"]: item for item in lexical
        }
        dense_ranks = {case_id: item.rank for case_id, item in dense_by_case.items()}
        lexical_ranks = {case_id: item.rank for case_id, item in lexical_by_case.items()}
        fused: dict[str, float] = defaultdict(float)
        for case_id, rank in dense_ranks.items():
            fused[case_id] += 1.0 / (RRF_K + rank)
        for case_id, rank in lexical_ranks.items():
            fused[case_id] += 1.0 / (RRF_K + rank)

        best_by_case: dict[str, str] = {}
        for case_id in fused:
            candidate_chunks = []
            if case_id in dense_by_case:
                candidate_chunks.append(dense_by_case[case_id].chunk_id)
            if case_id in lexical_by_case:
                candidate_chunks.append(lexical_by_case[case_id].chunk_id)
            best_by_case[case_id] = max(
                dict.fromkeys(candidate_chunks),
                key=lambda chunk_id: self._passage_relevance_score(
                    chunk_id, query, query_profile
                ),
            )
        if filters.outcome != "Any Outcome":
            best_by_case = {
                case_id: chunk_id
                for case_id, chunk_id in best_by_case.items()
                if self._matches_outcome_filter(
                    filters.outcome,
                    self._case_disposition(case_id)[2],
                    self._case_disposition(case_id)[0],
                )
            }
        rerank_pool_size = max(120, top_k * 10)
        best_by_case = {
            case_id: best_by_case[case_id]
            for case_id in sorted(
                best_by_case,
                key=lambda candidate: (-fused[candidate], candidate),
            )[:rerank_pool_size]
        }
        rrf_case_rank = {
            case_id: rank
            for rank, case_id in enumerate(
                sorted(best_by_case, key=lambda candidate: (-fused[candidate], candidate)),
                start=1,
            )
        }

        authority_by_case: dict[str, tuple[float, list[str], str]] = {}
        legal_relevance_by_case: dict[str, tuple[float, list[str], int, int]] = {}
        for case_id, chunk_id in best_by_case.items():
            authority_by_case[case_id] = self._authority_adjustment(
                case_id, chunk_id, query, query_signals
            )
            legal_relevance_by_case[case_id] = self._legal_relevance_adjustment(
                case_id, chunk_id, query, query_profile
            )
        ranked_cases = sorted(
            best_by_case.items(),
            key=lambda item: (
                -(
                    fused[item[0]]
                    + legal_relevance_by_case[item[0]][0]
                    + authority_by_case[item[0]][0]
                ),
                legal_relevance_by_case[item[0]][3],
                -legal_relevance_by_case[item[0]][2],
                item[0],
            ),
        )

        results: list[SearchResult] = []
        for case_id, chunk_id in ranked_cases[:top_k]:
            case = self._cases[case_id]
            chunk = self._chunks[chunk_id]
            case_issue_labels = self._case_issue_labels(case_id)
            case_signals = {signal.lower() for signal in case_issue_labels}
            shared = [signal for signal in query_signals if signal.lower() in case_signals]
            query_issue_order = (*query_profile.domains, *query_profile.concepts)
            legacy_issues = [str(issue) for issue in (case.get("legalIssues") or [])]
            display_issues = list(
                dict.fromkeys(
                    [
                        *(issue for issue in query_issue_order if issue in case_issue_labels),
                        *legacy_issues,
                    ]
                )
            )[:6]
            reason_codes: list[str] = []
            if case_id in dense_ranks:
                dense_kind = dense_by_case[case_id].match_kind
                reason_codes.append(
                    "Fact-pattern semantic match"
                    if dense_kind == "facts"
                    else "Holding/reasoning semantic match"
                )
            if case_id in lexical_ranks:
                reason_codes.append("Exact legal-term match")
            reason_codes.extend(f"Shared issue: {signal}" for signal in shared[:3])
            legal_adjustment, legal_reasons, _, _ = legal_relevance_by_case[case_id]
            reason_codes.extend(legal_reasons[:8])
            if (
                filters.court != "All Courts"
                or filters.year != "All Years"
                or filters.issue != "All Issues"
                or filters.outcome != "Any Outcome"
            ):
                reason_codes.append("Active filter match")
            if filters.outcome != "Any Outcome":
                reason_codes.append(f"Requested outcome match: {filters.outcome}")

            highlight = [token for token in lexical_tokens(query) if token in chunk["evidence"].lower()][:5]
            full_case_text = self._case_full_text(case_id)
            (
                matter_status,
                trial_status,
                winner,
                case_outcome,
                outcome_relief,
                outcome_evidence,
            ) = self._case_disposition(case_id)

            if all(case.get(field) for field in ("caseStage", "caseStageConfidence", "caseStageEvidence")):
                case_stage = str(case["caseStage"])
                stage_confidence = str(case["caseStageConfidence"])
                stage_evidence = str(case["caseStageEvidence"])
            else:
                stage = extract_case_stage(full_case_text, str(case["posture"]), list(case_issue_labels))
                case_stage = stage.stage
                stage_confidence = stage.confidence
                stage_evidence = stage.evidence
            if case_stage == "Trial ongoing":
                trial_status = "Trial ongoing"
            elif case_stage.startswith("Trial completed"):
                trial_status = "Trial completed"

            authority_score, authority_basis, bench_strength = authority_by_case[case_id]

            relevance_basis = list(reason_codes)
            if case_id in dense_ranks:
                relevance_basis.append(f"Dense semantic rank #{dense_ranks[case_id]}")
            if case_id in lexical_ranks:
                relevance_basis.append(f"Lexical term rank #{lexical_ranks[case_id]}")
            relevance_basis.append(f"Base hybrid RRF rank #{rrf_case_rank[case_id]}")
            relevance_basis.append(f"Legal-intent rerank adjustment {legal_adjustment:+.6f}")
            relevance_basis.append(f"Authority-aware final rank #{len(results) + 1}")
            results.append(
                SearchResult(
                    id=case_id,
                    rank=len(results) + 1,
                    title=case["title"],
                    court=case.get("courtName", case["court"]),
                    year=str(case["year"]),
                    category=case["category"],
                    citation=case["citation"],
                    posture=case["posture"],
                    legalIssues=display_issues,
                    filterIssues=list(case_issue_labels),
                    matchedEvidence=chunk["evidence"],
                    caseSummary=build_case_summary(chunk["evidence"], query),
                    highlightPhrases=highlight,
                    outcome=case_outcome,
                    matterStatus=matter_status,
                    trialStatus=trial_status,
                    winner=winner,
                    caseStage=case_stage,
                    caseStageConfidence=stage_confidence,
                    caseStageEvidence=stage_evidence,
                    outcomeRelief=outcome_relief,
                    outcomeEvidence=outcome_evidence,
                    relevanceBasis=relevance_basis,
                    authorityScore=authority_score,
                    authorityBasis=authority_basis,
                    benchStrength=bench_strength,
                    whyItMatched=reason_codes,
                    explanation={
                        "sharedFacts": chunk.get("context")
                        or f"Extracted from {chunk['paragraph']}; verify wording and context in the source document.",
                        "sharedLegalIssues": ", ".join(shared or display_issues),
                        "proceduralPosture": case["posture"],
                        "matchingTerms": highlight or shared or display_issues[:3],
                        "relation": "Requires human legal verification",
                    },
                    sourceUrl=case.get("sourceUrl")
                    or f"http://127.0.0.1:8001/documents/{quote(case_id, safe='')}",
                    evidenceLocator=EvidenceLocator(section=chunk["section"], paragraph=chunk["paragraph"]),
                    reasonCodes=reason_codes,
                    denseRank=dense_ranks.get(case_id),
                    lexicalRank=lexical_ranks.get(case_id),
                    retrievalScore=round(fused[case_id] + legal_adjustment + authority_score, 6),
                )
            )

        return SearchResponse(
            runId=str(uuid.uuid4()),
            corpusVersion=self.corpus_version,
            modelVersion=self.model_version,
            retrievalMethod=(
                f"Two-vector facts/decision dense retrieval + role-aware SQLite FTS5 + "
                f"case-level RRF(k={RRF_K}) + legal-intent/contradiction + authority reranking"
            ),
            extractedSignals=query_signals,
            latencyMs=round((time.perf_counter() - started) * 1000),
            caseCount=self.case_count,
            chunkCount=self.chunk_count,
            results=results,
        )

    def document_path(self, case_id: str) -> Path | None:
        case = self._cases.get(case_id)
        if not case or not case.get("pdfPath"):
            return None
        candidate = (PROJECT_ROOT / str(case["pdfPath"])).resolve()
        incoming_root = (PROJECT_ROOT / "data" / "incoming").resolve()
        try:
            candidate.relative_to(incoming_root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _ensure_citation_graph(self) -> None:
        """Lazily build a corpus-wide "which case's text names another case's citation" graph.

        Built once and cached: recent imported judgments rarely cite each other
        (most citations point outside this narrow corpus), so this is a sparse,
        high-precision signal rather than something computed per search.
        """

        if self._cites_out is not None and self._cited_by is not None:
            return
        with self._lock:
            if self._cites_out is not None and self._cited_by is not None:
                return
            citation_lookup: dict[str, str] = {}
            for case_id, case in self._cases.items():
                compact_citation = _compact_alnum(str(case.get("citation", "")))
                if len(compact_citation) >= 8 and any(ch.isdigit() for ch in compact_citation):
                    citation_lookup.setdefault(compact_citation, case_id)

            cites_out: dict[str, set[str]] = defaultdict(set)
            cited_by: dict[str, set[str]] = defaultdict(set)
            if citation_lookup:
                alternatives = sorted(citation_lookup, key=len, reverse=True)
                pattern = re.compile("|".join(re.escape(item) for item in alternatives))
                for case_id, case in self._cases.items():
                    own_citation = _compact_alnum(str(case.get("citation", "")))
                    compact_text = _compact_alnum(self._case_full_text(case_id))
                    for hit in set(pattern.findall(compact_text)):
                        if hit == own_citation:
                            continue
                        target_id = citation_lookup[hit]
                        if target_id == case_id:
                            continue
                        cites_out[case_id].add(target_id)
                        cited_by[target_id].add(case_id)
            self._cites_out = cites_out
            self._cited_by = cited_by

    def case_graph(self, case_ids: list[str], max_extra_neighbors: int = 15) -> GraphResponse:
        """Build an Obsidian-style connection graph for a set of result cases.

        Two distinct, honestly-labelled edge types: "cites" from detecting one
        case's own citation string inside another case's judgment text (a real
        textual link, not inferred), and "statute" from sharing a controlling
        statute (a softer, always-available fallback so the graph is not empty
        when this narrow corpus has no direct citations among the results).
        """

        seed_ids = [case_id for case_id in dict.fromkeys(case_ids) if case_id in self._cases]
        if not seed_ids:
            return GraphResponse(nodes=[], edges=[], citationEdgeCount=0, statuteEdgeCount=0)

        self._ensure_citation_graph()
        assert self._cites_out is not None and self._cited_by is not None
        seed_set = set(seed_ids)

        neighbor_ids: list[str] = []
        for case_id in seed_ids:
            for neighbor in sorted(self._cites_out.get(case_id, ())) + sorted(
                self._cited_by.get(case_id, ())
            ):
                if neighbor not in seed_set and neighbor not in neighbor_ids:
                    neighbor_ids.append(neighbor)
        neighbor_ids = neighbor_ids[:max_extra_neighbors]

        node_ids = seed_ids + neighbor_ids
        node_id_set = set(node_ids)

        edges: list[GraphEdge] = []
        edge_pairs_seen: set[tuple[str, str]] = set()

        for source in node_ids:
            for target in sorted(self._cites_out.get(source, ())):
                if target not in node_id_set:
                    continue
                pair = (source, target)
                if pair in edge_pairs_seen:
                    continue
                edge_pairs_seen.add(pair)
                target_case = self._cases[target]
                edges.append(
                    GraphEdge(
                        source=source,
                        target=target,
                        type="cites",
                        label=f"Cites {target_case['citation']}",
                    )
                )
        citation_edge_count = len(edges)

        statute_edge_count = 0
        for i, source in enumerate(node_ids):
            source_statutes = {
                statute.lower(): statute
                for statute in self._case_primary_profile(source).statutes
            }
            if not source_statutes:
                continue
            for target in node_ids[i + 1 :]:
                if (source, target) in edge_pairs_seen or (target, source) in edge_pairs_seen:
                    continue
                target_statutes = {
                    statute.lower() for statute in self._case_primary_profile(target).statutes
                }
                shared = sorted(source_statutes[key] for key in source_statutes if key in target_statutes)
                if not shared:
                    continue
                edge_pairs_seen.add((source, target))
                statute_edge_count += 1
                edges.append(
                    GraphEdge(
                        source=source,
                        target=target,
                        type="statute",
                        label="Same controlling statute: " + ", ".join(shared[:2]),
                    )
                )

        nodes = [
            GraphNode(
                id=case_id,
                title=str(self._cases[case_id]["title"]),
                citation=str(self._cases[case_id]["citation"]),
                court=str(self._cases[case_id].get("courtName", self._cases[case_id]["court"])),
                year=str(self._cases[case_id]["year"]),
                category=str(self._cases[case_id]["category"]),
                isResult=case_id in seed_set,
                sourceUrl=str(self._cases[case_id].get("sourceUrl"))
                if self._cases[case_id].get("sourceUrl")
                else f"http://127.0.0.1:8001/documents/{quote(case_id, safe='')}",
            )
            for case_id in node_ids
        ]

        return GraphResponse(
            nodes=nodes,
            edges=edges,
            citationEdgeCount=citation_edge_count,
            statuteEdgeCount=statute_edge_count,
        )
