from pathlib import Path
import json
import tempfile
import unittest

from tools.prepare_install import prepare
from tools.audit_release import audit, release_files


class InstallAndReleaseTests(unittest.TestCase):
    def test_staging_is_disabled_and_preserves_existing_file(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "stage"
            paths = prepare(destination, repo / "examples/settings.example.json")
            self.assertTrue(any("pyscript_modules/ai_energy_v11/config.py" in p for p in paths))
            settings = destination / "ai_energy_v11/settings.json"
            self.assertFalse(json.loads(settings.read_text())["enabled"])
            before = settings.read_bytes()
            with self.assertRaises(ValueError):
                prepare(destination, repo / "examples/settings.example.json")
            self.assertEqual(before, settings.read_bytes())
            self.assertFalse((destination / "configuration.yaml").exists())
            self.assertFalse((destination / "packages").exists())

    def test_release_allowlist_excludes_private_state_and_binary_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("README.md", "examples/settings.example.json", "settings.json",
                         "home_assistant/data/price.json", "local/private.py", "archive.zip",
                         "tools/__pycache__/cached.py", ".git/config", "docs/guide.md"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("{}")
            (root / "RELEASE_FILES.txt").write_text("README.md\nexamples/settings.example.json\ndocs/guide.md\n")
            paths = {p.relative_to(root).as_posix() for p in release_files(root)}
            self.assertEqual(paths, {"README.md", "examples/settings.example.json", "docs/guide.md"})

    def test_unreviewed_rendered_output_and_backup_never_join_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "README.md").write_text("Public source")
            for name in ("home_assistant/optional/ev-local.yaml", "examples/settings.backup.json"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Private user content without recognizable token patterns")
            (root / "RELEASE_FILES.txt").write_text("README.md\n")
            self.assertEqual([p.name for p in release_files(root)], ["README.md"])

    def test_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                list(release_files(Path(temp)))

    def test_publication_tree_passes_pattern_audit(self):
        files, findings = audit()
        self.assertGreater(len(files), 35)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
