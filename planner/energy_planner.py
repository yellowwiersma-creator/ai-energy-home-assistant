"""Pure, advisory scheduling for bounded flexible loads.

This is a new reference implementation, not a port or replacement of any existing
Home Assistant charging automation. It performs no I/O and issues no commands.
Prices must already be comparable retail EUR/kWh, including any applicable fees.
No thermal, battery, vehicle, occupancy, or comfort model is inferred: callers
must express permitted operation using the load's earliest start and deadline.

The policy is earliest deadline first, then highest priority. Each load receives
one uninterrupted block, choosing the cheapest complete candidate; when none
fits it receives the largest feasible partial block. Candidate starts are price
slot boundaries. The final slot can be partial. This greedy, discretized policy
does not guarantee a globally optimal schedule, even when all prices are known.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Literal, Mapping, Sequence


PriceSource = Literal["known", "forecast"]
SLOT_LENGTH = timedelta(minutes=15)
_EPSILON = 1e-9


def _datetime(value: datetime | str, label: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} must be an ISO 8601 timestamp with offset") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset/time zone")
    return value.astimezone(timezone.utc)


def _finite(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{label} must be finite and >= {minimum}" if minimum is not None
                         else f"{label} must be finite")
    return result


def _optional_price(value: Any, label: str) -> float | None:
    """An absent/non-finite price remains missing; it is never a zero tariff."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number or null")
    result = float(value)
    return result if math.isfinite(result) else None


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class PriceSlot:
    """One exact UTC quarter-hour; missing prices make the slot unavailable.

    ``uncertainty_eur_kwh`` is a caller-supplied nonnegative upward price
    scenario, not a statistical confidence guarantee. A forecast without this
    value is ineligible when a positive uncertainty weight is requested.
    """

    start: datetime
    retail_eur_kwh: float | None
    source: PriceSource
    uncertainty_eur_kwh: float | None = None

    def __post_init__(self) -> None:
        start = _datetime(self.start, "slot.start")
        if start.minute % 15 or start.second or start.microsecond:
            raise ValueError("price slots must start on a UTC quarter-hour boundary")
        if self.source not in ("known", "forecast"):
            raise ValueError("slot.source must be 'known' or 'forecast'")
        uncertainty = _optional_price(self.uncertainty_eur_kwh, "uncertainty_eur_kwh")
        if uncertainty is not None and uncertainty < 0:
            raise ValueError("uncertainty_eur_kwh must be nonnegative")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "retail_eur_kwh", _optional_price(self.retail_eur_kwh, "retail_eur_kwh"))
        object.__setattr__(self, "uncertainty_eur_kwh", uncertainty)

    @property
    def end(self) -> datetime:
        return self.start + SLOT_LENGTH

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PriceSlot:
        return cls(start=_datetime(data["start"], "slot.start"),
                   retail_eur_kwh=data.get("retail_eur_kwh"),
                   source=data["source"],
                   uncertainty_eur_kwh=data.get("uncertainty_eur_kwh"))


@dataclass(frozen=True)
class Load:
    name: str
    energy_kwh: float
    power_kw: float
    earliest: datetime
    deadline: datetime
    priority: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("load.name must be nonempty")
        energy = _finite(self.energy_kwh, "energy_kwh", minimum=0)
        power = _finite(self.power_kw, "power_kw", minimum=0)
        if power <= 0:
            raise ValueError("power_kw must be positive")
        earliest = _datetime(self.earliest, "load.earliest")
        deadline = _datetime(self.deadline, "load.deadline")
        if deadline < earliest:
            raise ValueError("deadline must not precede earliest")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer; higher wins equal deadlines")
        object.__setattr__(self, "energy_kwh", energy)
        object.__setattr__(self, "power_kw", power)
        object.__setattr__(self, "earliest", earliest)
        object.__setattr__(self, "deadline", deadline)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Load:
        return cls(name=data["name"], energy_kwh=data["energy_kwh"], power_kw=data["power_kw"],
                   earliest=_datetime(data["earliest"], "load.earliest"),
                   deadline=_datetime(data["deadline"], "load.deadline"),
                   priority=data.get("priority", 0))


@dataclass(frozen=True)
class Allocation:
    start: datetime
    end: datetime
    energy_kwh: float
    power_kw: float
    retail_eur_kwh: float
    source: PriceSource
    uncertainty_eur_kwh: float | None
    cost_eur: float
    objective_cost_eur: float


@dataclass(frozen=True)
class LoadPlan:
    name: str
    status: Literal["planned", "partial", "unplanned", "no_energy_required"]
    requested_energy_kwh: float
    scheduled_energy_kwh: float
    remaining_energy_kwh: float
    emergency_required: bool
    earliest: datetime
    deadline: datetime
    start: datetime | None
    end: datetime | None
    cost_eur: float
    objective_cost_eur: float
    price_basis: Literal["known", "forecast", "mixed", "none"]
    contains_forecast: bool
    uncertainty_complete: bool
    allocations: tuple[Allocation, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class PlanResult:
    site_power_kw: float
    uncertainty_weight: float
    planning_order: tuple[str, ...]
    loads: tuple[LoadPlan, ...]
    scheduled_energy_kwh: float
    remaining_energy_kwh: float
    cost_eur: float
    objective_cost_eur: float
    emergency_required: bool
    contains_forecast: bool
    advisory_only: bool = True
    policy: str = "EDF, then higher priority; greedy contiguous quarter-hour-start blocks; not globally optimal"

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


def _capacity_allows(start: datetime, end: datetime, power: float,
                     reservations: Sequence[Allocation], site_power: float) -> bool:
    # Evaluate actual overlapping power, not average energy over a quarter-hour.
    overlapping = [part for part in reservations if part.start < end and part.end > start]
    boundaries = {start, end}
    for part in overlapping:
        boundaries.add(max(start, part.start))
        boundaries.add(min(end, part.end))
    points = sorted(boundaries)
    return all(power + sum(part.power_kw for part in overlapping
                           if part.start < right and part.end > left) <= site_power + _EPSILON
               for left, right in zip(points, points[1:]))


def _candidate(load: Load, start: datetime, slot_map: Mapping[datetime, PriceSlot],
               reservations: Sequence[Allocation], site_power: float,
               weight: float) -> tuple[Allocation, ...]:
    parts: list[Allocation] = []
    remaining = load.energy_kwh
    cursor = start
    while remaining > _EPSILON and cursor < load.deadline:
        slot = slot_map.get(cursor)
        if slot is None or slot.retail_eur_kwh is None:
            break  # Missing prices and temporal gaps must not be bridged as free energy.
        if weight > 0 and slot.source == "forecast" and slot.uncertainty_eur_kwh is None:
            break
        available_seconds = (min(slot.end, load.deadline) - cursor).total_seconds()
        seconds = min(available_seconds, remaining / load.power_kw * 3600)
        end = cursor + timedelta(seconds=seconds)
        # datetime has microsecond resolution. Round required time upward rather
        # than inventing a tiny energy shortfall for an otherwise complete job.
        if (end - cursor).total_seconds() < seconds:
            end = min(end + timedelta(microseconds=1), slot.end, load.deadline)
        if end <= cursor or not _capacity_allows(cursor, end, load.power_kw, reservations, site_power):
            break
        energy = min(remaining, load.power_kw * ((end - cursor).total_seconds() / 3600))
        if energy <= _EPSILON:
            break
        price = slot.retail_eur_kwh
        objective_price = price + weight * (slot.uncertainty_eur_kwh or 0)
        if not math.isfinite(energy * price) or not math.isfinite(energy * objective_price):
            raise ValueError("price/energy/uncertainty magnitude exceeds finite cost range")
        parts.append(Allocation(cursor, end, energy, load.power_kw, price, slot.source,
                                slot.uncertainty_eur_kwh, energy * price, energy * objective_price))
        remaining = max(0.0, remaining - energy)
        cursor = end
        if end != slot.end:
            break
    return tuple(parts)


def plan_loads(slots: Sequence[PriceSlot], loads: Sequence[Load], *,
               site_power_kw: float, uncertainty_weight: float = 0.0) -> PlanResult:
    """Return suggestions; never relax a deadline or send an emergency command.

    ``site_power_kw`` is the capacity available to these flexible loads. The caller
    must already reserve any baseline/site demand. Earliest starts are rounded up
    by selecting only actual quarter-hour starts; deadlines are never rounded up.
    A partial block is advisory and must not automatically be executed where a
    real appliance needs an indivisible full cycle. ``emergency_required`` means
    unmet requested energy needs caller/user attention, not permission to override
    a manual, comfort, electrical, or safety constraint.
    """
    site_power = _finite(site_power_kw, "site_power_kw", minimum=0)
    weight = _finite(uncertainty_weight, "uncertainty_weight", minimum=0)
    slot_map: dict[datetime, PriceSlot] = {}
    for slot in slots:
        if slot.start in slot_map:
            raise ValueError(f"duplicate price slot at {slot.start.isoformat()}")
        slot_map[slot.start] = slot
    if len({load.name for load in loads}) != len(loads):
        raise ValueError("load names must be unique")
    starts = sorted(slot_map)
    ordered = sorted(enumerate(loads), key=lambda item: (item[1].deadline, -item[1].priority, item[0]))
    results: dict[int, LoadPlan] = {}
    reservations: list[Allocation] = []
    for index, load in ordered:
        candidates = [_candidate(load, start, slot_map, reservations, site_power, weight)
                      for start in starts if load.earliest <= start < load.deadline]
        candidates = [parts for parts in candidates if parts]
        complete = [parts for parts in candidates
                    if sum(part.energy_kwh for part in parts) >= load.energy_kwh - _EPSILON]
        if complete:
            chosen = min(complete, key=lambda parts: (sum(part.objective_cost_eur for part in parts), parts[0].start))
        elif candidates:
            chosen = min(candidates, key=lambda parts: (-sum(part.energy_kwh for part in parts),
                                                        sum(part.objective_cost_eur for part in parts), parts[0].start))
        else:
            chosen = ()
        scheduled = sum(part.energy_kwh for part in chosen)
        remaining = max(0.0, load.energy_kwh - scheduled)
        if remaining <= _EPSILON:
            remaining = 0.0
        emergency = remaining > 0
        issues: list[str] = []
        relevant = [slot_map[start] for start in starts if load.earliest <= start < load.deadline]
        if any(slot.retail_eur_kwh is None for slot in relevant):
            issues.append("missing_or_nonfinite_prices_in_window")
        first_boundary = load.earliest.replace(minute=load.earliest.minute // 15 * 15,
                                               second=0, microsecond=0)
        if first_boundary < load.earliest:
            first_boundary += SLOT_LENGTH
        if ((first_boundary < load.deadline and not relevant)
                or (relevant and (relevant[0].start > first_boundary or relevant[-1].end < load.deadline))
                or any(right.start != left.end for left, right in zip(relevant, relevant[1:]))):
            issues.append("price_gaps_in_window")
        if weight > 0 and any(slot.source == "forecast" and slot.uncertainty_eur_kwh is None for slot in relevant):
            issues.append("forecast_uncertainty_missing_in_window")
        if load.power_kw > site_power + _EPSILON:
            issues.append("load_power_exceeds_available_site_capacity")
        if emergency:
            issues.append("no_complete_contiguous_block_within_constraints")
        if load.earliest.minute % 15 or load.earliest.second or load.earliest.microsecond:
            issues.append("earliest_start_rounded_up_to_price_slot")
        sources = {part.source for part in chosen}
        basis = "mixed" if len(sources) > 1 else next(iter(sources), "none")
        results[index] = LoadPlan(
            name=load.name,
            status=("no_energy_required" if load.energy_kwh <= _EPSILON else
                    "planned" if not emergency else "partial" if chosen else "unplanned"),
            requested_energy_kwh=load.energy_kwh, scheduled_energy_kwh=scheduled,
            remaining_energy_kwh=remaining, emergency_required=emergency,
            earliest=load.earliest, deadline=load.deadline,
            start=chosen[0].start if chosen else None, end=chosen[-1].end if chosen else None,
            cost_eur=sum(part.cost_eur for part in chosen),
            objective_cost_eur=sum(part.objective_cost_eur for part in chosen),
            price_basis=basis, contains_forecast="forecast" in sources,
            uncertainty_complete=all(part.source == "known" or part.uncertainty_eur_kwh is not None for part in chosen),
            allocations=chosen, issues=tuple(issues),
        )
        reservations.extend(chosen)
    result_loads = tuple(results[index] for index in range(len(loads)))
    return PlanResult(site_power, weight, tuple(load.name for _, load in ordered), result_loads,
                      sum(item.scheduled_energy_kwh for item in result_loads),
                      sum(item.remaining_energy_kwh for item in result_loads),
                      sum(item.cost_eur for item in result_loads),
                      sum(item.objective_cost_eur for item in result_loads),
                      any(item.emergency_required for item in result_loads),
                      any(item.contains_forecast for item in result_loads))


@dataclass(frozen=True)
class PVDecision:
    decision: Literal["use_pv_now", "export_now_and_import_later", "equal", "unknown"]
    energy_kwh: float
    export_revenue_eur: float | None
    future_import_cost_eur: float | None
    advantage_of_using_pv_now_eur: float | None
    future_price_source: PriceSource
    advisory_only: bool = True
    assumption: str = ("Same flexible demand and energy now or later; import and export prices must use "
                       "a consistent marginal-cost basis. No storage losses, tariff settlement rules, "
                       "comfort costs or equipment effects are inferred.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


def pv_opportunity_cost(*, energy_kwh: float, export_eur_kwh_now: float | None,
                        future_import_eur_kwh: float | None,
                        future_price_source: PriceSource = "known") -> PVDecision:
    """Compare foregone PV export with buying the same demand's energy later.

    This is a marginal scenario calculation, not a universal financial rule or an
    instruction to store electricity. Consumers subject to netting or special fees
    must supply prices that represent their own comparable effective costs.
    """
    energy = _finite(energy_kwh, "energy_kwh", minimum=0)
    export_price = _optional_price(export_eur_kwh_now, "export_eur_kwh_now")
    import_price = _optional_price(future_import_eur_kwh, "future_import_eur_kwh")
    if future_price_source not in ("known", "forecast"):
        raise ValueError("future_price_source must be 'known' or 'forecast'")
    export = None if export_price is None else energy * export_price
    future_import = None if import_price is None else energy * import_price
    advantage = None if export is None or future_import is None else future_import - export
    if any(value is not None and not math.isfinite(value) for value in (export, future_import, advantage)):
        raise ValueError("PV price/energy magnitude exceeds finite cost range")
    decision = ("unknown" if advantage is None else "equal" if abs(advantage) <= _EPSILON
                else "use_pv_now" if advantage > 0 else "export_now_and_import_later")
    return PVDecision(decision, energy, export, future_import, advantage, future_price_source)
