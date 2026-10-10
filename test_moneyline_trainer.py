import copy
import csv
import importlib.util
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from moneyline_trainer import (
    FEATURE_FIELDS, TrainingRefused, chronological_plan,
    fit_experiment, metrics, read_dataset,
)

HAS_ML = (importlib.util.find_spec("sklearn") is not None and
          importlib.util.find_spec("numpy") is not None)

def fixture_rows(n=240):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [{"event_id": f"synthetic-{i}", "observation_key": f"obs-{i}",
             "captured_at": start+timedelta(days=i),
             "kickoff_time": start+timedelta(days=i, hours=2),
             "settled_at": start+timedelta(days=i, hours=6),
             "label": i%2, "baseline": 0.55+(i%5)*0.01,
             "features": [float(i%7), float(i%9), None]}
            for i in range(n)]

class MoneylineTrainerTests(unittest.TestCase):
    def test_empty_refused_before_model_import(self):
        with self.assertRaises(TrainingRefused) as caught:
            fit_experiment([])
        self.assertEqual(caught.exception.reason, "INSUFFICIENT_SETTLED_DATA")

    def test_fifteen_settled_games_still_refused(self):
        with self.assertRaises(TrainingRefused):
            chronological_plan(fixture_rows(15))

    def test_unique_events_required(self):
        rows = fixture_rows()
        rows[-1]["event_id"] = rows[0]["event_id"]
        with self.assertRaises(TrainingRefused) as caught:
            chronological_plan(rows)
        self.assertEqual(caught.exception.reason, "DUPLICATE_EVENTS")

    def test_split_is_chronological_and_disjoint(self):
        plan = chronological_plan(fixture_rows())
        self.assertLess(max(r["captured_at"] for r in plan["train"]),
                        min(r["captured_at"] for r in plan["calibration"]))
        self.assertLess(max(r["captured_at"] for r in plan["calibration"]),
                        min(r["captured_at"] for r in plan["test"]))

    def test_future_training_labels_are_purged(self):
        rows = fixture_rows()
        rows[10]["settled_at"] = rows[180]["captured_at"]
        plan = chronological_plan(rows)
        self.assertEqual(plan["details"]["training_labels_purged"], 1)
        self.assertNotIn("synthetic-10", {r["event_id"] for r in plan["train"]})

    def test_future_calibration_labels_are_purged(self):
        rows = fixture_rows()
        rows[170]["settled_at"] = rows[210]["captured_at"]
        with self.assertRaises(TrainingRefused) as caught:
            chronological_plan(rows)
        self.assertEqual(caught.exception.reason, "INSUFFICIENT_DATA_AFTER_TIME_PURGING")

    def test_same_time_groups_not_split(self):
        rows = fixture_rows()
        for row in rows:
            row["captured_at"] = rows[0]["captured_at"]
        with self.assertRaises(TrainingRefused) as caught:
            chronological_plan(rows)
        self.assertEqual(caught.exception.reason, "INSUFFICIENT_DISTINCT_TIME_GROUPS")

    def test_no_research_variation_refused(self):
        rows = fixture_rows()
        for row in rows:
            row["features"] = [1.0, None, None]
        with self.assertRaises(TrainingRefused) as caught:
            chronological_plan(rows)
        self.assertEqual(caught.exception.reason, "NO_USABLE_RESEARCH_VARIATION")

    def test_metrics(self):
        score = metrics([{"label": 1}], [0.75])
        self.assertAlmostEqual(score["brier_score"], 0.0625)
        self.assertAlmostEqual(score["log_loss"], -math.log(0.75))

    def test_header_only_csv_is_empty_dataset(self):
        fields = ["event_id", "observation_key", "captured_at", "kickoff_time",
                  "settled_at", "baseline_home_share", "home_won", "feature_version",
                  *FEATURE_FIELDS]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"synthetic.csv"
            with path.open("w", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields).writeheader()
            self.assertEqual(read_dataset(path), [])

    @unittest.skipUnless(HAS_ML, "Optional ML dependencies not installed")
    def test_actual_experimental_fit_never_approves_production(self):
        report, bundle, predictions = fit_experiment(fixture_rows())
        self.assertEqual(report["status"], "EXPERIMENTAL_FIT_NOT_APPROVED")
        self.assertFalse(report["production_approval"])
        self.assertFalse(report["parlay_gate_modified"])
        self.assertEqual(set(bundle["models"]), {"market_only", "market_plus_research"})
        self.assertEqual(len(predictions), 40)
        self.assertTrue(all(0 <= p["market_plus_research_probability"] <= 1 for p in predictions))

if __name__ == "__main__":
    unittest.main()
