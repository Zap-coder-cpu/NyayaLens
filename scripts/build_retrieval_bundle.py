"""Build the ignored, versioned retrieval corpus asset for a GitHub release."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = PROJECT_ROOT / "services" / "retrieval"
MANIFEST_PATH = SERVICE_ROOT / "bundle_manifest.json"
RELEASE_DIR = PROJECT_ROOT / ".release"
GITHUB_ASSET_LIMIT = 2 * 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundle_files() -> list[Path]:
    required = [
        SERVICE_ROOT / "data" / "import" / "cases.json",
        SERVICE_ROOT / "data" / "search.db",
        PROJECT_ROOT / "data" / "processed" / "judgments.csv",
        PROJECT_ROOT / "data" / "processed" / "ingestion_qa.csv",
    ]
    incoming = sorted((PROJECT_ROOT / "data" / "incoming").rglob("*"))
    files = [*required, *(path for path in incoming if path.is_file())]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Cannot build bundle; missing: " + ", ".join(missing))
    return list(dict.fromkeys(files))


def verify_index(manifest: dict[str, object]) -> None:
    database = SERVICE_ROOT / "data" / "search.db"
    connection = sqlite3.connect(database)
    try:
        metadata = dict(connection.execute("SELECT key, value FROM index_meta"))
        case_count = connection.execute("SELECT COUNT(DISTINCT case_id) FROM chunks").fetchone()[0]
        chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vector_count = connection.execute("SELECT COUNT(*) FROM case_embeddings").fetchone()[0]
    finally:
        connection.close()
    expected = {
        "caseCount": case_count,
        "chunkCount": chunk_count,
        "vectorCount": vector_count,
        "schemaVersion": metadata.get("schema_version"),
        "vectorSelectorVersion": metadata.get("vector_selector_version"),
        "lexicalSelectorVersion": metadata.get("lexical_selector_version"),
    }
    mismatches = [
        f"{key}: manifest={manifest.get(key)!r}, index={value!r}"
        for key, value in expected.items()
        if str(manifest.get(key)) != str(value)
    ]
    if mismatches:
        raise RuntimeError("Bundle manifest does not match the built index: " + "; ".join(mismatches))


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    verify_index(manifest)
    files = bundle_files()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    destination = RELEASE_DIR / str(manifest["assetName"])
    temporary = destination.with_suffix(destination.suffix + ".partial")
    if temporary.exists():
        temporary.unlink()

    print(f"Building {destination.name} from {len(files):,} files...", flush=True)
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for index, path in enumerate(files, start=1):
                compression = zipfile.ZIP_STORED if path.suffix.lower() == ".pdf" else zipfile.ZIP_DEFLATED
                archive.write(
                    path,
                    path.relative_to(PROJECT_ROOT).as_posix(),
                    compress_type=compression,
                    compresslevel=None if compression == zipfile.ZIP_STORED else 6,
                )
                if index == 1 or index == len(files) or index % 250 == 0:
                    print(f"Packed {index:,}/{len(files):,} files", flush=True)
        if temporary.stat().st_size > GITHUB_ASSET_LIMIT:
            raise RuntimeError(
                f"Bundle is {temporary.stat().st_size / 1024 / 1024:.0f} MiB, above GitHub's "
                "2 GiB per-asset limit. Split-source bundle support is required before release."
            )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    print(f"Asset: {destination}", flush=True)
    print(f"Bytes: {destination.stat().st_size}", flush=True)
    print(f"SHA-256: {sha256(destination)}", flush=True)
    print("Copy this checksum into services/retrieval/bundle_manifest.json before publishing.")


if __name__ == "__main__":
    main()
