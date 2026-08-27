import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "setup_retrieval.py"
SPEC = importlib.util.spec_from_file_location("setup_retrieval", SCRIPT_PATH)
assert SPEC and SPEC.loader
setup_retrieval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_retrieval)


class ReleaseSetupTests(unittest.TestCase):
    def test_bundle_manifest_is_finalized(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "services" / "retrieval" / "bundle_manifest.json").read_text())
        self.assertRegex(manifest["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(manifest["releaseTag"], "retrieval-corpus-v2")
        self.assertEqual(manifest["caseCount"], 4609)
        self.assertEqual(manifest["chunkCount"], 151653)
        self.assertEqual(manifest["vectorCount"], 9218)
        self.assertEqual(manifest["schemaVersion"], "4")
        self.assertEqual(manifest["vectorSelectorVersion"], "facts-decision-v3")
        self.assertEqual(manifest["lexicalSelectorVersion"], "source-passages-v2")

    def test_safe_extraction_accepts_only_runtime_directories(self) -> None:
        original_root = setup_retrieval.PROJECT_ROOT
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                setup_retrieval.PROJECT_ROOT = root
                valid = root / "valid.zip"
                with zipfile.ZipFile(valid, "w") as archive:
                    archive.writestr("services/retrieval/data/import/cases.json", "{}")
                setup_retrieval.extract_safely(valid)
                self.assertEqual(
                    (root / "services" / "retrieval" / "data" / "import" / "cases.json").read_text(),
                    "{}",
                )

                invalid = root / "invalid.zip"
                with zipfile.ZipFile(invalid, "w") as archive:
                    archive.writestr("data/incoming/../../.env", "secret")
                with self.assertRaises(RuntimeError):
                    setup_retrieval.extract_safely(invalid)
                self.assertFalse((root / ".env").exists())
        finally:
            setup_retrieval.PROJECT_ROOT = original_root

    def test_existing_bundle_must_match_index_version_and_counts(self) -> None:
        original_service_root = setup_retrieval.SERVICE_ROOT
        original_required = setup_retrieval.REQUIRED_BUNDLE_FILES
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                service_root = root / "services" / "retrieval"
                database = service_root / "data" / "search.db"
                required = (
                    service_root / "data" / "import" / "cases.json",
                    database,
                    root / "data" / "processed" / "judgments.csv",
                    root / "data" / "processed" / "ingestion_qa.csv",
                )
                for path in required:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path != database:
                        path.write_text("fixture", encoding="utf-8")
                with sqlite3.connect(database) as connection:
                    connection.execute("CREATE TABLE index_meta(key TEXT, value TEXT)")
                    connection.executemany(
                        "INSERT INTO index_meta VALUES (?, ?)",
                        [
                            ("schema_version", "4"),
                            ("vector_selector_version", "facts-decision-v3"),
                            ("lexical_selector_version", "source-passages-v2"),
                        ],
                    )
                    connection.execute("CREATE TABLE chunks(case_id TEXT)")
                    connection.executemany("INSERT INTO chunks VALUES (?)", [("a",), ("b",)])
                    connection.execute("CREATE TABLE case_embeddings(embedding_id TEXT)")
                    connection.executemany(
                        "INSERT INTO case_embeddings VALUES (?)",
                        [("a:facts",), ("a:decision",), ("b:facts",), ("b:decision",)],
                    )
                connection.close()
                setup_retrieval.SERVICE_ROOT = service_root
                setup_retrieval.REQUIRED_BUNDLE_FILES = required
                manifest = {
                    "caseCount": 2,
                    "chunkCount": 2,
                    "vectorCount": 4,
                    "schemaVersion": "4",
                    "vectorSelectorVersion": "facts-decision-v3",
                    "lexicalSelectorVersion": "source-passages-v2",
                }
                self.assertTrue(setup_retrieval.installed_bundle_matches(manifest))
                self.assertFalse(
                    setup_retrieval.installed_bundle_matches({**manifest, "vectorCount": 2})
                )
        finally:
            setup_retrieval.SERVICE_ROOT = original_service_root
            setup_retrieval.REQUIRED_BUNDLE_FILES = original_required


if __name__ == "__main__":
    unittest.main()
