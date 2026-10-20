"""Build a curated source ZIP only after the local publication audit passes."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile

from audit_release import REPO, audit


def build(output: Path):
    output = output.resolve()
    if output.exists():
        raise ValueError("Release output already exists; choose a new filename.")
    files, findings = audit()
    if findings:
        raise ValueError(f"Publication audit found {len(findings)} issue(s). Run audit_release.py.")
    if not files:
        raise ValueError("No release files selected.")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            content = path.read_bytes()
            relative = path.relative_to(REPO).as_posix()
            archive.writestr("ai-energy/" + relative, content)
            manifest.append({"path": relative, "bytes": len(content),
                             "sha256": hashlib.sha256(content).hexdigest()})
        archive.writestr("ai-energy/RELEASE-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    return {"file_count": len(files), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"No public archive built: {exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
