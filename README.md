# Nyayalens

A sober, source-linked precedent retrieval prototype for lawyers and judicial researchers. It combines local semantic embeddings with SQLite full-text search, then fuses both rankings with reciprocal-rank fusion (RRF). Search runs without a paid API or API key.

This remains a research prototype, not a comprehensive legal database or legal-advice system. When generated import data is present, the current local corpus contains 4,609 Supreme Court and High Court judgments split into 151,653 source-located passages. Otherwise, the service falls back to five bundled demonstration decisions. Every result opens either the exact source URL extracted from the PDF or the local source PDF for human verification.

## Retrieval flow

1. The TanStack server validates the query and filters and proxies the request; the browser never receives service credentials.
2. The Python service embeds the query locally with `BAAI/bge-small-en-v1.5` through ONNX Runtime.
3. Dense cosine retrieval scores separate fact-pattern and decision/holding vectors for every judgment; SQLite FTS5 ranks source passages.
4. Passage-role and primary-proceeding checks demote party submissions and quoted precedents before judgment-level RRF fusion and legal-context reranking.
5. The API returns source locators, reason codes and retrieval traces—not invented relevance percentages.

## Local setup (Windows PowerShell)

### Fast setup from the versioned release bundle

After cloning the repository, install the frontend and start the application:

```powershell
npm install
npm run dev:all
```

On the first run, `dev:all` invokes the setup automatically. It downloads the checksum-verified `retrieval-corpus-v2` GitHub release bundle, creates the Python environment, installs pinned dependencies and downloads the public embedding model. Existing local indexes are checked against the manifest's case, passage, vector and schema versions and are replaced when stale. For a private repository, authenticate GitHub CLI with `gh auth login` or provide `GH_TOKEN` first.

The setup can also be run separately:

```powershell
npm run setup:retrieval
```

The manual setup below remains available for rebuilding the corpus from source PDFs.

Install the frontend:

```powershell
npm install
```

Create the retrieval environment and install its pinned dependencies:

```powershell
python -m venv services/retrieval/.venv
services/retrieval/.venv/Scripts/python.exe -m pip install -r services/retrieval/requirements.txt
```

Download the public embedding model once. This requires internet access but no account or API key. Runtime search is offline after this step.

```powershell
services/retrieval/.venv/Scripts/python.exe services/retrieval/bootstrap_model.py
```

Place source PDFs below the ignored `data/incoming` directory, then build the normalized CSV, QA report and search corpus:

```powershell
services/retrieval/.venv/Scripts/python.exe services/retrieval/ingest.py
```

The importer writes `data/processed/judgments.csv` with the exact columns `id,title,court,date,citation,case_number,issues,source_url,pdf_filename`, plus `data/processed/ingestion_qa.csv`. It uses embedded PDF text first and local OCR only for low-quality files. Missing citations and source URLs remain blank instead of being guessed.

Start the retrieval service:

```powershell
services/retrieval/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir services/retrieval --host 127.0.0.1 --port 8001
```

In a second terminal, start the website:

```powershell
npm run dev
```

The default service URL is `http://127.0.0.1:8001`. Copy `.env.example` to `.env.local` only when the URL or optional shared secret needs to change.

## Verification

```powershell
npm run typecheck
npm run lint
npm run build
services/retrieval/.venv/Scripts/python.exe -m unittest discover -s services/retrieval/tests -v
services/retrieval/.venv/Scripts/python.exe services/retrieval/evaluate.py
```

The bundled evaluation in `services/retrieval/evaluation/golden_queries.json` applies to the five demonstration decisions. When the imported corpus is active, the command uses `import_regression_queries.json` instead. The report treats unreviewed results as unknown, reports judged coverage with its metrics and supports explicit contradiction labels. The current small set catches regressions; it is not a substitute for 30–50 independently lawyer-reviewed queries across legal domains.

## Configuration and security

- No Indian Kanoon token, hosted-embedding key or generative-model key is used.
- `RETRIEVAL_SERVICE_URL` is read only by the TanStack server.
- `RETRIEVAL_SERVICE_SECRET` is optional for local use and recommended when the retrieval service is remotely reachable.
- `RETRIEVAL_REQUEST_TIMEOUT_MS` optionally overrides the website-to-retrieval timeout (120 seconds by default, capped at 300 seconds) for slower first searches on CPU-only laptops.
- Queries are limited and validated at both the TypeScript and Python boundaries.
- The model cache, generated SQLite index, virtual environment and local environment files are excluded from Git.
- Submitted case descriptions may contain sensitive data; use anonymized facts and add authentication, encryption, retention controls and audit logging before any institutional deployment.

## Scaling path

SQLite FTS5 and exact cosine search are appropriate for this local 4,609-judgment demonstrator. A production corpus should use a licensed and traceable ingestion pipeline, immutable source versions, paragraph-level citation checks, an approximate-nearest-neighbor vector index, hybrid reranking, access controls and a lawyer-reviewed evaluation set. The detailed implementation and rollout plan is in [`docs/semantic-search-execution-plan.md`](docs/semantic-search-execution-plan.md).

## Lovable synchronization

This repository is connected to [Lovable](https://lovable.dev/projects/59548ad3-f32b-4a87-af08-1e4c9c4e3064). Keep pushed history linear and do not force-push or rewrite published commits.
