# Local retrieval service

This service provides keyless, local hybrid precedent retrieval over imported Supreme Court and High Court PDFs, with a small bundled fallback corpus.

## Setup

From the repository root, the preferred setup uses the versioned GitHub release bundle:

```powershell
npm install
npm run dev:all
```

On its first run, `dev:all` invokes the setup automatically. The downloader verifies the bundle SHA-256 before extraction. The release contains the generated corpus, SQLite index, QA exports and source PDFs required by local document links. It never downloads or writes an environment file. Use `npm run setup:retrieval` when setup should be run separately.

Maintainers create a replacement ignored release asset only after the index metadata matches
`bundle_manifest.json`:

```powershell
services/retrieval/.venv/Scripts/python scripts/build_retrieval_bundle.py
```

The builder validates case, passage, vector and selector versions, enforces GitHub's per-asset size
limit and prints the SHA-256 that must be copied into the manifest before the release is published.

To rebuild everything manually instead:

```powershell
python -m venv services/retrieval/.venv
services/retrieval/.venv/Scripts/python -m pip install -r services/retrieval/requirements.txt
services/retrieval/.venv/Scripts/python services/retrieval/bootstrap_model.py
```

The bootstrap command downloads the public `BAAI/bge-small-en-v1.5` ONNX embedding model into the ignored local cache. No account or API key is required. Runtime service startup is offline-only; document embeddings are computed once and cached in SQLite.

Index generation defaults to one memory-conscious embedding process. On a machine with ample RAM,
`RETRIEVAL_INDEX_WORKERS=2` may be set temporarily to speed up a rebuild; it is optional and does
not affect ranking output.

The search request does not require court or year. Their defaults are `All Courts` and `All Years`,
so an ordinary natural-language query searches the complete available corpus. Explicit Advanced
Search choices remain hard filters.

## Accuracy pipeline

The local, keyless ranking pipeline uses:

1. two complementary embeddings per judgment: material factual context and decision/holding with a short operative result;
2. SQLite FTS5 passage retrieval with role-aware judgment deduplication;
3. judgment-level Reciprocal Rank Fusion, with one dense vote per judgment even though two vectors are searched;
4. primary-versus-mentioned extraction for legal domain, concepts, Act–provision pairs, relief, posture, relationships and signed material facts;
5. demotion of party submissions, case headers and unadopted quoted authorities;
6. contradiction penalties for facts such as investigation complete/pending, trial delayed/completed,
   flight or witness risk present/absent, and Hindu/Muslim personal-law mismatch; and
7. authority and bench strength only as a final, small tie-breaker after substantive relevance.

Vector-schema upgrades preserve the large lexical index and rebuild only the ignored semantic table
when the corpus is unchanged. The first startup after such an upgrade can take several minutes on a
normal laptop; later startups reuse the index.

## Import PDFs

Place PDFs below `data/incoming`, then run:

```powershell
services/retrieval/.venv/Scripts/python services/retrieval/ingest.py
```

The importer extracts metadata and passages, uses local OCR only when embedded text is unusable, writes the exact requested manifest to `data/processed/judgments.csv`, and writes review flags to `data/processed/ingestion_qa.csv`. Generated source material and indexes are excluded from Git.

## Run

```powershell
services/retrieval/.venv/Scripts/python -m uvicorn app.main:app --app-dir services/retrieval --host 127.0.0.1 --port 8001
```

In another terminal, run `npm run dev`. The TanStack server proxies validated search requests to the local service.

## Verify

```powershell
services/retrieval/.venv/Scripts/python -m unittest discover -s services/retrieval/tests -v
services/retrieval/.venv/Scripts/python services/retrieval/evaluate.py
```

Rankings are retrieval outputs, not legal-accuracy probabilities. Every result must be verified against its linked judgment. Rows marked `review_required` in the QA report remain searchable when their judgment text is sound, but their incomplete metadata should be reviewed before institutional use.
