from datetime import datetime, timezone

from .config import LEGACY_NORMALIZED_DIR
from .storage import (
    legacy_month_files,
    read_json,
    write_json_atomic,
)
from .quality import (
    QUALITY_VERSION,
    assess_legacy_record,
)


LEGACY_VERSION = "11.1.0-legacy-reader"


def scan_legacy_history():
    files = legacy_month_files()

    summary = {
        "version": LEGACY_VERSION,
        "quality_version": QUALITY_VERSION,

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "files": len(files),

        "records_total": 0,

        "classification": {
            "VALID": 0,
            "PARTIAL": 0,
            "SOURCE_MISSING": 0,
            "QUARANTINE": 0,
        },

        "learning": {
            "price_eligible": 0,
            "margin_eligible": 0,
            "weather_eligible": 0,
            "energy_eligible": 0,
        },

        "missing": {
            "market": 0,
            "weather_context": 0,
            "zonneplan": 0,
            "timestamp": 0,
        },

        "first_timestamp": None,
        "last_timestamp": None,

        "per_file": [],
    }

    first_dt = None
    last_dt = None

    for path in files:
        rows = read_json(
            path,
            default=[],
        )

        if not isinstance(rows, list):
            rows = []

        file_result = {
            "file": str(path),
            "records": len(rows),

            "VALID": 0,
            "PARTIAL": 0,
            "SOURCE_MISSING": 0,
            "QUARANTINE": 0,

            "price_eligible": 0,
            "weather_eligible": 0,
        }

        for record in rows:
            summary["records_total"] += 1

            assessment = (
                assess_legacy_record(
                    record
                )
            )

            classification = (
                assessment.get(
                    "classification",
                    "QUARANTINE",
                )
            )

            if classification not in (
                "VALID",
                "PARTIAL",
                "SOURCE_MISSING",
                "QUARANTINE",
            ):
                classification = (
                    "QUARANTINE"
                )

            summary[
                "classification"
            ][classification] += 1

            file_result[
                classification
            ] += 1

            if assessment.get(
                "price_learning_eligible"
            ):
                summary[
                    "learning"
                ][
                    "price_eligible"
                ] += 1

                file_result[
                    "price_eligible"
                ] += 1

            if assessment.get(
                "margin_learning_eligible"
            ):
                summary[
                    "learning"
                ][
                    "margin_eligible"
                ] += 1

            if assessment.get(
                "weather_learning_eligible"
            ):
                summary[
                    "learning"
                ][
                    "weather_eligible"
                ] += 1

                file_result[
                    "weather_eligible"
                ] += 1

            if assessment.get(
                "energy_learning_eligible"
            ):
                summary[
                    "learning"
                ][
                    "energy_eligible"
                ] += 1

            reasons = assessment.get(
                "reasons",
                [],
            )

            if "market_missing" in reasons:
                summary[
                    "missing"
                ]["market"] += 1

            if (
                "weather_context_incomplete"
                in reasons
            ):
                summary[
                    "missing"
                ][
                    "weather_context"
                ] += 1

            if "zonneplan_missing" in reasons:
                summary[
                    "missing"
                ]["zonneplan"] += 1

            if (
                "timestamp_missing_or_invalid"
                in reasons
            ):
                summary[
                    "missing"
                ]["timestamp"] += 1

            timestamp = assessment.get(
                "timestamp"
            )

            if timestamp is not None:
                try:
                    dt = datetime.fromisoformat(
                        timestamp
                    )

                    if (
                        first_dt is None
                        or dt < first_dt
                    ):
                        first_dt = dt

                    if (
                        last_dt is None
                        or dt > last_dt
                    ):
                        last_dt = dt

                except Exception:
                    pass

        summary[
            "per_file"
        ].append(file_result)

    if first_dt is not None:
        summary[
            "first_timestamp"
        ] = first_dt.isoformat()

    if last_dt is not None:
        summary[
            "last_timestamp"
        ] = last_dt.isoformat()

    total = summary[
        "records_total"
    ]

    if total > 0:
        summary[
            "valid_pct"
        ] = round(
            (
                summary[
                    "classification"
                ]["VALID"]
                / total
            )
            * 100,
            2,
        )

        summary[
            "price_learning_pct"
        ] = round(
            (
                summary[
                    "learning"
                ]["price_eligible"]
                / total
            )
            * 100,
            2,
        )

    else:
        summary["valid_pct"] = 0
        summary["price_learning_pct"] = 0

    LEGACY_NORMALIZED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        LEGACY_NORMALIZED_DIR
        / "legacy_scan_summary.json"
    )

    write_json_atomic(
        report_path,
        summary,
    )

    summary[
        "report_file"
    ] = str(report_path)

    return summary
