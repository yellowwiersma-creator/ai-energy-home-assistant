from datetime import datetime, timezone
from pathlib import Path
import json

from .config import (
    CONFIG_VERSION,
    DATA_DIRECTORIES,
    LOG_DIR,
    LEGACY_RAW_DIR,
)


STORAGE_VERSION = "11.1.0-native-storage"


def ensure_directories():
    created = []

    for directory in DATA_DIRECTORIES:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        created.append(str(directory))

    return created


def read_json(path, default=None):
    path = Path(path)

    if default is None:
        default = {}

    try:
        if not path.exists():
            return default

        text = path.read_text(
            encoding="utf-8"
        )

        return json.loads(text)

    except Exception:
        return default


def write_json_atomic(path, payload):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    text = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        sort_keys=False,
    )

    temp_path.write_text(
        text,
        encoding="utf-8",
    )

    temp_path.replace(path)

    return str(path)


def legacy_month_files():
    """
    Geeft alleen de bestaande oude raw JSON-bestanden terug.

    Deze functie verandert de oude AI Energy-data nooit.
    """

    if not LEGACY_RAW_DIR.exists():
        return []

    files = []

    for path in LEGACY_RAW_DIR.rglob("*.json"):
        if path.is_file():
            files.append(path)

    files.sort(
        key=lambda item: str(item)
    )

    return files


def legacy_storage_summary():
    files = legacy_month_files()

    result = {
        "legacy_raw_directory":
            str(LEGACY_RAW_DIR),

        "exists":
            LEGACY_RAW_DIR.exists(),

        "files":
            len(files),

        "total_bytes":
            0,

        "total_mb":
            0,

        "first_file":
            None,

        "last_file":
            None,
    }

    if files:
        result["first_file"] = str(
            files[0]
        )

        result["last_file"] = str(
            files[-1]
        )

    total_bytes = 0

    for path in files:
        try:
            total_bytes += path.stat().st_size
        except Exception:
            pass

    result["total_bytes"] = total_bytes

    result["total_mb"] = round(
        total_bytes / 1024 / 1024,
        3,
    )

    return result


def storage_self_test():
    """
    Controleert nieuwe V11-opslag en bevestigt
    dat de legacy raw-map zichtbaar is.
    """

    directories = ensure_directories()

    legacy = legacy_storage_summary()

    now = datetime.now(
        timezone.utc
    )

    result = {
        "status": "ok",

        "config_version":
            CONFIG_VERSION,

        "storage_version":
            STORAGE_VERSION,

        "timestamp_utc":
            now.isoformat(),

        "directories_created":
            len(directories),

        "directories":
            directories,

        "legacy_raw_exists":
            legacy.get("exists"),

        "legacy_raw_files":
            legacy.get("files"),

        "legacy_raw_mb":
            legacy.get("total_mb"),

        "legacy_first_file":
            legacy.get("first_file"),

        "legacy_last_file":
            legacy.get("last_file"),
    }

    test_path = (
        LOG_DIR
        / "storage_self_test.json"
    )

    write_json_atomic(
        test_path,
        result,
    )

    result["test_file"] = str(
        test_path
    )

    return result
