from datetime import date, datetime, timedelta, timezone

from .config import (
    MARKET_DIR,
    LEGACY_NORMALIZED_DIR,
    LOG_DIR,
)

from .storage import (
    read_json,
    write_json_atomic,
)


BACKFILL_VERSION = "11.2.2-nordpool-backfill"

NORDPOOL_DIR = (
    MARKET_DIR
    / "nordpool"
)

LEGACY_SCAN_FILE = (
    LEGACY_NORMALIZED_DIR
    / "legacy_scan_summary.json"
)

BACKFILL_REPORT_FILE = (
    LOG_DIR
    / "nordpool_backfill_last.json"
)

BACKFILL_STATE_FILE = (
    LOG_DIR
    / "nordpool_backfill_state.json"
)

MAX_FAILURE_ATTEMPTS = 2


def parse_date(value):
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    try:
        text = str(
            value
        ).strip()

        if not text:
            return None

        return date.fromisoformat(
            text[0:10]
        )

    except Exception:
        return None


def _legacy_date_range():
    payload = read_json(
        LEGACY_SCAN_FILE,
        default={},
    )

    if not isinstance(
        payload,
        dict,
    ):
        return None, None

    first_date = parse_date(
        payload.get(
            "first_timestamp"
        )
    )

    last_date = parse_date(
        payload.get(
            "last_timestamp"
        )
    )

    return (
        first_date,
        last_date,
    )


def _load_backfill_state():
    payload = read_json(
        BACKFILL_STATE_FILE,
        default={},
    )

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    failures = payload.get(
        "failures"
    )

    if not isinstance(
        failures,
        dict,
    ):
        failures = {}

    permanent_missing = payload.get(
        "permanent_missing"
    )

    if not isinstance(
        permanent_missing,
        list,
    ):
        permanent_missing = []

    return {
        "version":
            BACKFILL_VERSION,

        "failures":
            failures,

        "permanent_missing":
            permanent_missing,
    }


def _save_backfill_state(state):
    if not isinstance(
        state,
        dict,
    ):
        state = {}

    state["version"] = (
        BACKFILL_VERSION
    )

    state["updated_utc"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    write_json_atomic(
        BACKFILL_STATE_FILE,
        state,
    )


def nordpool_day_path(
    delivery_date
):
    value = parse_date(
        delivery_date
    )

    if value is None:
        return None

    return (
        NORDPOOL_DIR
        / str(value.year)
        / (
            value.isoformat()
            + ".json"
        )
    )


def inspect_nordpool_day(
    delivery_date
):
    value = parse_date(
        delivery_date
    )

    if value is None:
        return {
            "date": None,
            "exists": False,
            "complete": False,
            "valid_slots": 0,
            "expected_slots": None,
            "file": None,
        }

    path = nordpool_day_path(
        value
    )

    payload = read_json(
        path,
        default={},
    )

    exists = (
        path is not None
        and path.exists()
    )

    complete = False
    valid_slots = 0
    expected_slots = None

    if isinstance(
        payload,
        dict,
    ):
        complete = (
            payload.get(
                "complete_day"
            )
            is True
        )

        valid_slots = (
            payload.get(
                "valid_slots",
                0,
            )
        )

        expected_slots = (
            payload.get(
                "expected_slots"
            )
        )

    return {
        "date":
            value.isoformat(),

        "exists":
            exists,

        "complete":
            complete,

        "valid_slots":
            valid_slots,

        "expected_slots":
            expected_slots,

        "file":
            str(path)
            if path is not None
            else None,
    }


def build_nordpool_backfill_plan(
    start_date=None,
    end_date=None,
    max_days=14,
):
    legacy_first, legacy_last = (
        _legacy_date_range()
    )

    start = parse_date(
        start_date
    )

    end = parse_date(
        end_date
    )

    if start is None:
        start = legacy_first

    if end is None:
        end = legacy_last

    try:
        limit = int(
            max_days
        )

    except Exception:
        limit = 14

    if limit < 1:
        limit = 1

    if limit > 31:
        limit = 31

    if (
        start is None
        or end is None
    ):
        return {
            "version":
                BACKFILL_VERSION,

            "status":
                "no_range",

            "planned_dates":
                [],

            "missing_total":
                0,
        }

    if end < start:
        return {
            "version":
                BACKFILL_VERSION,

            "status":
                "invalid_range",

            "start_date":
                start.isoformat(),

            "end_date":
                end.isoformat(),

            "planned_dates":
                [],

            "missing_total":
                0,
        }

    state = (
        _load_backfill_state()
    )

    permanent_missing = set(
        state.get(
            "permanent_missing",
            [],
        )
    )

    missing_dates = []

    existing_complete = 0
    existing_incomplete = 0
    permanent_count = 0
    total_days = 0

    current = start

    while current <= end:
        total_days += 1

        date_text = (
            current.isoformat()
        )

        inspection = (
            inspect_nordpool_day(
                current
            )
        )

        if inspection.get(
            "complete"
        ):
            existing_complete += 1

        elif date_text in permanent_missing:
            permanent_count += 1

        else:
            missing_dates.append(
                date_text
            )

            if inspection.get(
                "exists"
            ):
                existing_incomplete += 1

        current = (
            current
            + timedelta(days=1)
        )

    planned_dates = (
        missing_dates[
            0:limit
        ]
    )

    return {
        "version":
            BACKFILL_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "start_date":
            start.isoformat(),

        "end_date":
            end.isoformat(),

        "total_days":
            total_days,

        "existing_complete":
            existing_complete,

        "existing_incomplete":
            existing_incomplete,

        "permanent_missing":
            permanent_count,

        "missing_total":
            len(
                missing_dates
            ),

        "batch_limit":
            limit,

        "planned_count":
            len(
                planned_dates
            ),

        "planned_dates":
            planned_dates,

        "remaining_after_plan":
            max(
                0,
                len(missing_dates)
                - len(planned_dates),
            ),
    }


def finalize_nordpool_backfill(
    plan,
    fetch_results,
):
    if not isinstance(
        plan,
        dict,
    ):
        plan = {}

    if not isinstance(
        fetch_results,
        list,
    ):
        fetch_results = []

    state = (
        _load_backfill_state()
    )

    failures_state = state.get(
        "failures",
        {},
    )

    permanent_missing = set(
        state.get(
            "permanent_missing",
            [],
        )
    )

    # Seed eventueel mislukkingen uit
    # het vorige rapport.
    #
    # Hierdoor vergeten we de laatste
    # mislukte run niet na deze upgrade.
    previous_report = read_json(
        BACKFILL_REPORT_FILE,
        default={},
    )

    if isinstance(
        previous_report,
        dict,
    ):
        previous_failures = (
            previous_report.get(
                "failures",
                []
            )
        )

        if isinstance(
            previous_failures,
            list,
        ):
            for item in previous_failures:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                date_text = item.get(
                    "date"
                )

                if date_text is None:
                    continue

                date_text = str(
                    date_text
                )

                if date_text not in failures_state:
                    failures_state[
                        date_text
                    ] = {
                        "attempts": 1,

                        "last_status":
                            item.get(
                                "status"
                            ),

                        "last_error":
                            item.get(
                                "error"
                            ),
                    }

    successful = 0
    failed = 0
    complete_slots = 0

    failures = []

    newly_permanent = []

    for result in fetch_results:
        if not isinstance(
            result,
            dict,
        ):
            failed += 1
            continue

        date_text = result.get(
            "date"
        )

        if date_text is not None:
            date_text = str(
                date_text
            )

        complete = (
            result.get(
                "complete_day"
            )
            is True
        )

        if complete:
            successful += 1

            try:
                complete_slots += int(
                    result.get(
                        "valid_slots",
                        0,
                    )
                )

            except Exception:
                pass

            if (
                date_text is not None
                and date_text
                in failures_state
            ):
                failures_state.pop(
                    date_text,
                    None,
                )

            permanent_missing.discard(
                date_text
            )

            continue

        failed += 1

        status = result.get(
            "status"
        )

        error = result.get(
            "error"
        )

        if date_text is not None:
            previous = (
                failures_state.get(
                    date_text,
                    {},
                )
            )

            try:
                attempts = int(
                    previous.get(
                        "attempts",
                        0,
                    )
                )

            except Exception:
                attempts = 0

            attempts += 1

            failures_state[
                date_text
            ] = {
                "attempts":
                    attempts,

                "last_status":
                    status,

                "last_error":
                    error,

                "last_attempt_utc":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
            }

            if (
                attempts
                >= MAX_FAILURE_ATTEMPTS
            ):
                permanent_missing.add(
                    date_text
                )

                newly_permanent.append(
                    date_text
                )

        failures.append(
            {
                "date":
                    date_text,

                "status":
                    status,

                "error":
                    error,

                "attempts":
                    (
                        failures_state
                        .get(
                            date_text,
                            {},
                        )
                        .get(
                            "attempts"
                        )
                        if date_text
                        is not None
                        else None
                    ),
            }
        )

    state["failures"] = (
        failures_state
    )

    state["permanent_missing"] = (
        sorted(
            permanent_missing
        )
    )

    _save_backfill_state(
        state
    )

    next_plan = (
        build_nordpool_backfill_plan(
            start_date=
                plan.get(
                    "start_date"
                ),

            end_date=
                plan.get(
                    "end_date"
                ),

            max_days=
                plan.get(
                    "batch_limit",
                    14,
                ),
        )
    )

    remaining = (
        next_plan.get(
            "missing_total",
            0,
        )
    )

    permanent_total = (
        next_plan.get(
            "permanent_missing",
            0,
        )
    )

    if (
        remaining == 0
        and failed == 0
    ):
        status = "complete"

    elif (
        remaining == 0
        and permanent_total > 0
    ):
        status = (
            "complete_with_gaps"
        )

    elif successful > 0:
        status = "progress"

    elif failed > 0:
        status = "partial"

    else:
        status = "idle"

    result = {
        "version":
            BACKFILL_VERSION,

        "status":
            status,

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "start_date":
            plan.get(
                "start_date"
            ),

        "end_date":
            plan.get(
                "end_date"
            ),

        "total_days":
            plan.get(
                "total_days"
            ),

        "existing_complete_before":
            plan.get(
                "existing_complete"
            ),

        "planned":
            plan.get(
                "planned_count"
            ),

        "successful":
            successful,

        "failed":
            failed,

        "slots_stored":
            complete_slots,

        "remaining":
            remaining,

        "permanent_missing":
            permanent_total,

        "newly_permanent":
            newly_permanent,

        "next_dates":
            next_plan.get(
                "planned_dates",
                [],
            ),

        "failures":
            failures,

        "state_file":
            str(
                BACKFILL_STATE_FILE
            ),
    }

    write_json_atomic(
        BACKFILL_REPORT_FILE,
        result,
    )

    result["report_file"] = str(
        BACKFILL_REPORT_FILE
    )

    return result
