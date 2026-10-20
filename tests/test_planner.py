"""Behavioral tests for the standalone advisory planner (stdlib only)."""

import json
import math
import unittest
from datetime import datetime, timedelta, timezone

from planner import Load, PriceSlot, plan_loads, pv_opportunity_cost


BASE = datetime(2030, 1, 1, tzinfo=timezone.utc)


def prices(values, sources=None, uncertainties=None):
    return [PriceSlot(BASE + timedelta(minutes=15 * index), price,
                      sources[index] if sources else "known",
                      uncertainties[index] if uncertainties else None)
            for index, price in enumerate(values)]


def load(name="flexible", energy=1, power=4, earliest_minutes=0, deadline_minutes=60, priority=0):
    return Load(name, energy, power, BASE + timedelta(minutes=earliest_minutes),
                BASE + timedelta(minutes=deadline_minutes), priority)


def assert_capacity(test, result, maximum):
    allocations = [part for job in result.loads for part in job.allocations]
    times = sorted({part.start for part in allocations} | {part.end for part in allocations})
    for left, right in zip(times, times[1:]):
        total = sum(part.power_kw for part in allocations if part.start < right and part.end > left)
        test.assertLessEqual(total, maximum + 1e-9)


class PlannerTests(unittest.TestCase):
    def test_full_slot_chooses_cheapest_complete_block(self):
        result = plan_loads(prices([0.40, 0.10, 0.20]), [load(deadline_minutes=45)], site_power_kw=4)
        job = result.loads[0]
        self.assertEqual(job.start, BASE + timedelta(minutes=15))
        self.assertEqual(job.end, BASE + timedelta(minutes=30))
        self.assertAlmostEqual(job.cost_eur, 0.10)
        self.assertEqual(job.status, "planned")
        self.assertFalse(result.emergency_required)

    def test_partial_last_slot_has_weighted_energy_cost(self):
        result = plan_loads(prices([0.20, 0.40]), [load(energy=1.5, deadline_minutes=30)], site_power_kw=4)
        job = result.loads[0]
        self.assertEqual([part.energy_kwh for part in job.allocations], [1.0, 0.5])
        self.assertEqual(job.end, BASE + timedelta(minutes=22, seconds=30))
        self.assertAlmostEqual(job.cost_eur, 0.40)
        self.assertEqual(job.remaining_energy_kwh, 0)

    def test_fractional_microsecond_duration_does_not_create_false_emergency(self):
        result = plan_loads(prices([0.2]), [load(energy=2, power=22, deadline_minutes=15)], site_power_kw=22)
        self.assertEqual(result.loads[0].scheduled_energy_kwh, 2)
        self.assertEqual(result.loads[0].remaining_energy_kwh, 0)
        self.assertFalse(result.emergency_required)

    def test_negative_prices_remain_valid_and_preferred(self):
        job = plan_loads(prices([-0.10, -0.30]), [load(deadline_minutes=30)], site_power_kw=4).loads[0]
        self.assertEqual(job.start, BASE + timedelta(minutes=15))
        self.assertAlmostEqual(job.cost_eur, -0.30)

    def test_none_nan_infinity_are_not_zero_prices(self):
        for bad in (None, math.nan, math.inf, -math.inf):
            with self.subTest(price=bad):
                result = plan_loads(prices([bad, 0.20]), [load(deadline_minutes=30)], site_power_kw=4)
                self.assertEqual(result.loads[0].start, BASE + timedelta(minutes=15))
                self.assertAlmostEqual(result.cost_eur, 0.20)
                self.assertIn("missing_or_nonfinite_prices_in_window", result.loads[0].issues)
                json.dumps(result.to_dict(), allow_nan=False)

    def test_real_zero_tariff_is_valid(self):
        job = plan_loads(prices([0, 0.20]), [load(deadline_minutes=30)], site_power_kw=4).loads[0]
        self.assertEqual(job.start, BASE)
        self.assertEqual(job.cost_eur, 0)

    def test_noninterruptible_job_does_not_skip_expensive_middle(self):
        job = plan_loads(prices([0.10, 1.0, 0.10]), [load(energy=2, deadline_minutes=45)], site_power_kw=4).loads[0]
        self.assertAlmostEqual(job.cost_eur, 1.10)
        self.assertEqual(len(job.allocations), 2)
        self.assertEqual(job.allocations[0].end, job.allocations[1].start)

    def test_price_gap_breaks_block_and_partial_remains_contiguous(self):
        slots = prices([0.10, 0.20, 0.30])
        del slots[1]
        result = plan_loads(slots, [load(energy=2, deadline_minutes=45)], site_power_kw=4)
        job = result.loads[0]
        self.assertEqual(job.status, "partial")
        self.assertEqual(job.scheduled_energy_kwh, 1)
        self.assertEqual(job.remaining_energy_kwh, 1)
        self.assertTrue(job.emergency_required)
        self.assertIn("price_gaps_in_window", job.issues)

    def test_missing_price_breaks_contiguous_block(self):
        job = plan_loads(prices([0.1, None, 0.1]), [load(energy=2, deadline_minutes=45)], site_power_kw=4).loads[0]
        self.assertEqual(job.scheduled_energy_kwh, 1)
        self.assertEqual(len(job.allocations), 1)

    def test_forecast_and_mixed_labels_follow_selected_slots(self):
        slots = prices([0.1, 0.2], ["known", "forecast"])
        mixed = plan_loads(slots, [load(energy=2, deadline_minutes=30)], site_power_kw=4)
        self.assertEqual(mixed.loads[0].price_basis, "mixed")
        self.assertTrue(mixed.contains_forecast)
        self.assertFalse(mixed.loads[0].uncertainty_complete)
        known = plan_loads(slots, [load(deadline_minutes=30)], site_power_kw=4)
        self.assertEqual(known.loads[0].price_basis, "known")
        self.assertFalse(known.contains_forecast)

    def test_conservative_objective_can_choose_known_over_cheaper_forecast(self):
        slots = prices([0.10, 0.20], ["forecast", "known"], [0.20, None])
        neutral = plan_loads(slots, [load(deadline_minutes=30)], site_power_kw=4)
        cautious = plan_loads(slots, [load(deadline_minutes=30)], site_power_kw=4, uncertainty_weight=1)
        self.assertEqual(neutral.loads[0].price_basis, "forecast")
        self.assertEqual(cautious.loads[0].price_basis, "known")
        self.assertEqual(cautious.loads[0].start, BASE + timedelta(minutes=15))

    def test_missing_forecast_uncertainty_not_assumed_zero_when_risk_enabled(self):
        result = plan_loads(prices([0.10], ["forecast"]), [load(deadline_minutes=15)],
                            site_power_kw=4, uncertainty_weight=1)
        self.assertEqual(result.loads[0].status, "unplanned")
        self.assertEqual(result.remaining_energy_kwh, 1)
        self.assertIn("forecast_uncertainty_missing_in_window", result.loads[0].issues)

    def test_shared_capacity_serializes_two_jobs(self):
        result = plan_loads(prices([0.1, 0.2]),
                            [load("first", deadline_minutes=30), load("second", deadline_minutes=30)], site_power_kw=4)
        self.assertEqual(result.loads[0].start, BASE)
        self.assertEqual(result.loads[1].start, BASE + timedelta(minutes=15))
        self.assertFalse(result.emergency_required)
        assert_capacity(self, result, 4)

    def test_shared_capacity_allows_safe_parallel_jobs(self):
        result = plan_loads(prices([0.1]),
                            [load("first", power=3, energy=0.75, deadline_minutes=15),
                             load("second", power=3, energy=0.75, deadline_minutes=15)], site_power_kw=6)
        self.assertEqual([job.start for job in result.loads], [BASE, BASE])
        self.assertFalse(result.emergency_required)
        assert_capacity(self, result, 6)

    def test_partial_slot_reserves_peak_power_not_average_power(self):
        result = plan_loads(prices([0.1]),
                            [load("first", energy=0.5, deadline_minutes=15),
                             load("second", energy=0.5, deadline_minutes=15)], site_power_kw=4)
        self.assertEqual(result.loads[0].status, "planned")
        self.assertEqual(result.loads[1].status, "unplanned")
        assert_capacity(self, result, 4)

    def test_deadline_first_then_priority_preserves_result_input_order(self):
        result = plan_loads(prices([0.1, 0.2, 0.3]),
                            [load("late-high", deadline_minutes=45, priority=100),
                             load("early", deadline_minutes=15, priority=-1),
                             load("late-low", deadline_minutes=45, priority=0)], site_power_kw=4)
        self.assertEqual(result.planning_order, ("early", "late-high", "late-low"))
        self.assertEqual([job.name for job in result.loads], ["late-high", "early", "late-low"])
        self.assertFalse(result.emergency_required)

    def test_impossible_deadline_keeps_deadline_and_reports_shortfall(self):
        result = plan_loads(prices([0.1, 0.2, -1.0]), [load(energy=3, deadline_minutes=30)], site_power_kw=4)
        job = result.loads[0]
        self.assertEqual(job.end, job.deadline)
        self.assertEqual(job.scheduled_energy_kwh, 2)
        self.assertEqual(job.remaining_energy_kwh, 1)
        self.assertTrue(job.emergency_required)
        self.assertEqual(job.status, "partial")

    def test_non_grid_deadline_can_end_with_partial_slot_but_never_extend(self):
        job = plan_loads(prices([0.1, 0.2]), [load(energy=2, deadline_minutes=20)], site_power_kw=4).loads[0]
        self.assertEqual(job.end, BASE + timedelta(minutes=20))
        self.assertAlmostEqual(job.scheduled_energy_kwh, 4 / 3)
        self.assertAlmostEqual(job.remaining_energy_kwh, 2 / 3)

    def test_earliest_constraint_rounds_up_never_starts_early(self):
        job = plan_loads(prices([-1, 0.2]), [load(earliest_minutes=7, deadline_minutes=30)], site_power_kw=4).loads[0]
        self.assertEqual(job.start, BASE + timedelta(minutes=15))
        self.assertIn("earliest_start_rounded_up_to_price_slot", job.issues)

    def test_power_limit_is_not_overridden_for_emergency(self):
        result = plan_loads(prices([0.1]), [load(deadline_minutes=15)], site_power_kw=3)
        self.assertEqual(result.scheduled_energy_kwh, 0)
        self.assertEqual(result.remaining_energy_kwh, 1)
        self.assertTrue(result.emergency_required)

    def test_empty_horizon_is_unplanned_and_zero_energy_requires_no_action(self):
        result = plan_loads([], [load("need"), load("empty", energy=0)], site_power_kw=4)
        self.assertEqual(result.loads[0].status, "unplanned")
        self.assertIn("price_gaps_in_window", result.loads[0].issues)
        self.assertEqual(result.loads[1].status, "no_energy_required")
        self.assertFalse(result.loads[1].emergency_required)

    def test_json_input_output_contract(self):
        slot = PriceSlot.from_dict({"start": "2030-01-01T01:00:00+01:00", "retail_eur_kwh": 0.2, "source": "known"})
        job = Load.from_dict({"name": "example", "energy_kwh": 1, "power_kw": 4,
                              "earliest": "2030-01-01T00:00:00Z", "deadline": "2030-01-01T00:15:00Z"})
        result = plan_loads([slot], [job], site_power_kw=4)
        payload = json.loads(json.dumps(result.to_dict(), allow_nan=False))
        self.assertEqual(payload["loads"][0]["start"], "2030-01-01T00:00:00Z")
        self.assertTrue(payload["advisory_only"])

    def test_dst_fall_repeated_wall_hour_has_distinct_utc_slots(self):
        first = datetime.fromisoformat("2026-10-25T02:00:00+02:00")
        repeated = datetime.fromisoformat("2026-10-25T02:00:00+01:00")
        slots = [PriceSlot(first + timedelta(minutes=i * 15), 0.2, "known") for i in range(4)]
        slots.append(PriceSlot(repeated, 0.2, "known"))
        job = Load("dst", 5, 4, first, datetime.fromisoformat("2026-10-25T02:15:00+01:00"))
        result = plan_loads(slots, [job], site_power_kw=4)
        self.assertFalse(result.emergency_required)
        self.assertEqual(result.loads[0].end - result.loads[0].start, timedelta(minutes=75))

    def test_dst_spring_wall_hour_gap_is_contiguous_in_utc(self):
        first = datetime.fromisoformat("2026-03-29T01:45:00+01:00")
        after = datetime.fromisoformat("2026-03-29T03:00:00+02:00")
        slots = [PriceSlot(first, 0.2, "known"), PriceSlot(after, 0.3, "known")]
        job = Load("dst", 2, 4, first, datetime.fromisoformat("2026-03-29T03:15:00+02:00"))
        result = plan_loads(slots, [job], site_power_kw=4)
        self.assertFalse(result.emergency_required)
        self.assertEqual(result.loads[0].end - result.loads[0].start, timedelta(minutes=30))

    def test_rejects_naive_or_unaligned_slots_and_ambiguous_duplicates(self):
        with self.assertRaises(ValueError):
            PriceSlot(datetime(2030, 1, 1), 0.2, "known")
        with self.assertRaises(ValueError):
            PriceSlot(BASE + timedelta(minutes=1), 0.2, "known")
        with self.assertRaises(ValueError):
            plan_loads(prices([0.1]) * 2, [load()], site_power_kw=4)
        with self.assertRaises(ValueError):
            plan_loads(prices([0.1]), [load(), load()], site_power_kw=4)

    def test_rejects_invalid_numeric_constraints_and_source(self):
        for kwargs in ({"power": 0}, {"energy": -1}, {"energy": math.nan}, {"priority": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                load(**kwargs)
        with self.assertRaises(ValueError):
            PriceSlot(BASE, True, "known")
        with self.assertRaises(ValueError):
            PriceSlot(BASE, 0.2, "unknown")
        with self.assertRaises(ValueError):
            PriceSlot(BASE, 0.2, "forecast", -0.1)
        with self.assertRaises(ValueError):
            plan_loads(prices([0.2]), [load()], site_power_kw=math.inf)


class PVTests(unittest.TestCase):
    def test_export_is_an_opportunity_cost(self):
        result = pv_opportunity_cost(energy_kwh=2, export_eur_kwh_now=0.10, future_import_eur_kwh=0.30)
        self.assertEqual(result.decision, "use_pv_now")
        self.assertAlmostEqual(result.advantage_of_using_pv_now_eur, 0.40)
        self.assertAlmostEqual(result.export_revenue_eur, 0.20)

    def test_high_export_or_negative_later_import_can_favor_later_demand(self):
        result = pv_opportunity_cost(energy_kwh=1, export_eur_kwh_now=0.30, future_import_eur_kwh=-0.10,
                                     future_price_source="forecast")
        self.assertEqual(result.decision, "export_now_and_import_later")
        self.assertAlmostEqual(result.advantage_of_using_pv_now_eur, -0.40)
        self.assertEqual(result.future_price_source, "forecast")

    def test_missing_pv_price_is_unknown_not_free(self):
        for price in (None, math.nan):
            result = pv_opportunity_cost(energy_kwh=1, export_eur_kwh_now=price, future_import_eur_kwh=0.3)
            self.assertEqual(result.decision, "unknown")
            self.assertIsNone(result.advantage_of_using_pv_now_eur)
            json.dumps(result.to_dict(), allow_nan=False)

    def test_equal_prices_have_no_claimed_financial_advantage(self):
        result = pv_opportunity_cost(energy_kwh=1, export_eur_kwh_now=0.2, future_import_eur_kwh=0.2)
        self.assertEqual(result.decision, "equal")
        self.assertEqual(result.advantage_of_using_pv_now_eur, 0)


if __name__ == "__main__":
    unittest.main()
