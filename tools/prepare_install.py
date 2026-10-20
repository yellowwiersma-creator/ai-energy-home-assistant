"""Prepare a new local HA install folder; refuse to overwrite existing files."""
from pathlib import Path
import argparse
import importlib
import json
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _has_link(path: Path) -> bool:
    return any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
               for p in [path, *path.parents])


def prepare(destination: Path, settings_path: Path) -> list[str]:
    if _has_link(destination.absolute()):
        raise ValueError("Staging through a symbolic link or junction is not supported")
    destination = destination.resolve()
    if destination == REPO or REPO in destination.parents and destination != REPO / "install-stage":
        raise ValueError("Choose an external staging folder, or the ignored install-stage folder.")
    sys.path.insert(0, str(REPO / "home_assistant/pyscript_modules"))
    config = importlib.import_module("ai_energy_v11.config")
    settings = config.validate_settings(json.loads(settings_path.read_text(encoding="utf-8")))
    from tools.audit_release import release_files
    source = REPO / "home_assistant"
    entries = [(p, destination / p.relative_to(source)) for p in release_files(REPO)
               if p.suffix == ".py" and p.is_relative_to(source)
               and p.relative_to(source).parts[0] in {"pyscript_modules", "pyscript"}]
    target_settings = destination / "ai_energy_v11/settings.json"
    targets = [target_settings] + [target for _, target in entries]
    if destination.exists():
        raise ValueError("Choose a new staging directory. Existing directories are never reused.")
    destination.mkdir(parents=True, exist_ok=False)
    # A disabled settings file is staged before any automatically loaded script.
    # Enabling collection is always a separate local choice after setup.
    settings["enabled"] = False
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    with target_settings.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    for original, target in entries:
        target.parent.mkdir(parents=True, exist_ok=True)
        if _has_link(target) or destination not in target.resolve().parents:
            raise ValueError("Staging path changed or escapes destination")
        with original.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    return [str(p.relative_to(destination)).replace("\\", "/") for p in targets]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--settings", type=Path, default=REPO / "examples/settings.example.json")
    args = parser.parse_args()
    try:
        paths = prepare(args.destination, args.settings)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Install folder not prepared: {exc}\n")
    print(f"Prepared {len(paths)} files. Collection is OFF; no existing files were overwritten.")
    print("No device-control recipe or Home Assistant root configuration was installed.")


if __name__ == "__main__":
    main()
