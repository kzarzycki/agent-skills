import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH_SCRIPT = ROOT / "scripts" / "hash-artifact.py"
MACOS_SCRIPT = ROOT / "scripts" / "macos-app-provenance.sh"


def run_hash(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HASH_SCRIPT), *(str(path) for path in paths)],
        text=True,
        capture_output=True,
        check=False,
    )


def run_macos_probe(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(MACOS_SCRIPT), str(path)],
        text=True,
        capture_output=True,
        check=False,
    )


class HashArtifactTest(unittest.TestCase):
    def test_hash_artifact_emits_json_for_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "artifact.bin"
            artifact.write_bytes(b"abc")

            result = run_hash(artifact)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload,
            [
                {
                    "path": str(artifact),
                    "bytes": 3,
                    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                }
            ],
        )

    def test_hash_artifact_fails_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.tar.gz"

            result = run_hash(missing)

        self.assertEqual(result.returncode, 2)
        self.assertIn("not a regular file", result.stderr)

    def test_macos_probe_refuses_non_macos_here(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Example.app"
            app.mkdir()

            result = run_macos_probe(app)

        self.assertEqual(result.returncode, 2)
        self.assertIn("macOS only", result.stderr)


if __name__ == "__main__":
    unittest.main()
