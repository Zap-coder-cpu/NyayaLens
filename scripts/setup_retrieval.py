"""Install the local retrieval runtime and its versioned GitHub release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = PROJECT_ROOT / "services" / "retrieval"
MANIFEST_PATH = SERVICE_ROOT / "bundle_manifest.json"
REQUIRED_BUNDLE_FILES = (
    SERVICE_ROOT / "data" / "import" / "cases.json",
    SERVICE_ROOT / "data" / "search.db",
    PROJECT_ROOT / "data" / "processed" / "judgments.csv",
    PROJECT_ROOT / "data" / "processed" / "ingestion_qa.csv",
)


def installed_bundle_matches(manifest: dict[str, object]) -> bool:
    """Detect stale local bundles instead of silently accepting any existing DB."""

    if not all(path.is_file() for path in REQUIRED_BUNDLE_FILES):
        return False
    database = SERVICE_ROOT / "data" / "search.db"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database)
        metadata = dict(connection.execute("SELECT key, value FROM index_meta"))
        case_count = connection.execute(
            "SELECT COUNT(DISTINCT case_id) FROM chunks"
        ).fetchone()[0]
        chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vector_count = connection.execute("SELECT COUNT(*) FROM case_embeddings").fetchone()[0]
    except (OSError, sqlite3.Error):
        return False
    finally:
        if connection is not None:
            connection.close()
    expected_metadata = {
        "schema_version": manifest.get("schemaVersion"),
        "vector_selector_version": manifest.get("vectorSelectorVersion"),
        "lexical_selector_version": manifest.get("lexicalSelectorVersion"),
    }
    return (
        case_count == manifest.get("caseCount")
        and chunk_count == manifest.get("chunkCount")
        and vector_count == manifest.get("vectorCount")
        and all(str(metadata.get(key)) == str(value) for key, value in expected_metadata.items())
    )


def venv_python() -> Path:
    suffix = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return SERVICE_ROOT / ".venv" / suffix


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def ensure_environment() -> Path:
    python = venv_python()
    if not python.is_file():
        print("Creating retrieval virtual environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(SERVICE_ROOT / ".venv")
    run([str(python), "-m", "pip", "install", "-r", str(SERVICE_ROOT / "requirements.txt")])
    return python


def download_with_http(url: str, destination: Path, accept: str | None = None) -> None:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    headers = {"User-Agent": "precedent-finder-retrieval-setup"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response, destination.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            copied = 0
            while block := response.read(1024 * 1024):
                output.write(block)
                copied += len(block)
                if total:
                    print(f"Downloaded {copied / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MiB", end="\r")
        print()
    except urllib.error.HTTPError as error:
        if error.code in {401, 403, 404}:
            raise RuntimeError(
                "The release asset is not publicly accessible. For a private repository, install "
                "GitHub CLI and run 'gh auth login', or set GH_TOKEN before running setup again."
            ) from error
        raise


def download_bundle(manifest: dict[str, object], destination: Path) -> None:
    repository = str(manifest["repository"])
    tag = str(manifest["releaseTag"])
    asset = str(manifest["assetName"])
    gh = shutil.which("gh")
    if gh:
        result = subprocess.run(
            [gh, "release", "download", tag, "--repo", repository, "--pattern", asset, "--dir", str(destination.parent)],
            cwd=PROJECT_ROOT,
            check=False,
        )
        downloaded = destination.parent / asset
        if result.returncode == 0 and downloaded.is_file():
            if downloaded != destination:
                downloaded.replace(destination)
            return
        print("GitHub CLI download was unavailable; trying the release URL directly...", flush=True)
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        api_url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "precedent-finder-retrieval-setup",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request) as response:
            release = json.load(response)
        release_asset = next((item for item in release["assets"] if item["name"] == asset), None)
        if release_asset is None:
            raise RuntimeError(f"Release {tag} does not contain {asset}")
        download_with_http(str(release_asset["url"]), destination, "application/octet-stream")
        return
    url = f"https://github.com/{repository}/releases/download/{tag}/{asset}"
    download_with_http(url, destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_safely(bundle: Path) -> None:
    root = PROJECT_ROOT.resolve()
    allowed_prefixes = ("data/incoming/", "data/processed/", "services/retrieval/data/")
    allowed_roots = tuple((root / prefix.rstrip("/")).resolve() for prefix in allowed_prefixes)
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/").lstrip("/")
            if not normalized or info.is_dir():
                continue
            if not normalized.startswith(allowed_prefixes):
                raise RuntimeError(f"Unexpected bundle path: {normalized}")
            destination = (root / normalized).resolve()
            if not any(destination == allowed or destination.is_relative_to(allowed) for allowed in allowed_roots):
                raise RuntimeError(f"Unsafe bundle path: {normalized}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Download and replace an existing corpus bundle")
    parser.add_argument("--skip-model", action="store_true", help="Do not download/verify the embedding model")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_hash = str(manifest["sha256"])
    if expected_hash == "PENDING":
        raise SystemExit("The retrieval bundle manifest has not been finalized by the maintainer.")

    if args.force or not installed_bundle_matches(manifest):
        with tempfile.TemporaryDirectory(prefix="precedent-retrieval-") as temporary:
            bundle = Path(temporary) / str(manifest["assetName"])
            print(f"Downloading corpus {manifest['corpusVersion']}...", flush=True)
            download_bundle(manifest, bundle)
            actual_hash = sha256(bundle)
            if actual_hash.lower() != expected_hash.lower():
                raise RuntimeError(f"Bundle checksum mismatch: expected {expected_hash}, received {actual_hash}")
            print("Checksum verified; extracting corpus...", flush=True)
            extract_safely(bundle)
    else:
        print("Current retrieval corpus and index are already present.", flush=True)

    python = ensure_environment()
    if not args.skip_model:
        run([str(python), str(SERVICE_ROOT / "bootstrap_model.py")])

    missing = [str(path.relative_to(PROJECT_ROOT)) for path in REQUIRED_BUNDLE_FILES if not path.is_file()]
    if missing:
        raise RuntimeError("Setup completed with missing files: " + ", ".join(missing))
    print(
        f"Retrieval setup complete: {manifest['caseCount']} judgments and "
        f"{manifest['chunkCount']} searchable passages.",
        flush=True,
    )


if __name__ == "__main__":
    main()
