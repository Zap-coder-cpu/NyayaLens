from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .engine import SemanticEngine
from .models import GraphRequest, GraphResponse, HealthResponse, SearchRequest, SearchResponse


app = FastAPI(
    title="Nyayalens Retrieval Service",
    version="0.1.0",
    description="Keyless local hybrid retrieval over a source-linked evaluation corpus.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Retrieval-Secret"],
)


@lru_cache(maxsize=1)
def get_engine() -> SemanticEngine:
    return SemanticEngine()


def verify_service_secret(x_retrieval_secret: str | None = Header(default=None)) -> None:
    expected = os.getenv("RETRIEVAL_SERVICE_SECRET", "").strip()
    if expected and x_retrieval_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid retrieval service credential")


@app.get("/health", response_model=HealthResponse)
def health(engine: SemanticEngine = Depends(get_engine)) -> HealthResponse:
    return HealthResponse(
        status="ready",
        corpusVersion=engine.corpus_version,
        modelVersion=engine.model_version,
        caseCount=engine.case_count,
        chunkCount=engine.chunk_count,
    )


@app.post("/search", response_model=SearchResponse, dependencies=[Depends(verify_service_secret)])
def search(request: SearchRequest, engine: SemanticEngine = Depends(get_engine)) -> SearchResponse:
    return engine.search(request.query, request.filters, request.top_k)


@app.post("/graph", response_model=GraphResponse, dependencies=[Depends(verify_service_secret)])
def graph(request: GraphRequest, engine: SemanticEngine = Depends(get_engine)) -> GraphResponse:
    return engine.case_graph(request.caseIds)


@app.get("/documents/{case_id}")
def document(case_id: str, engine: SemanticEngine = Depends(get_engine)) -> FileResponse:
    path = engine.document_path(case_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Source document is not available")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
