import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import train_moneyline_model as writer


class ArtifactIdentityTests(unittest.TestCase):
    def test_saved_artifact_hash_matches_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset.csv"
            dataset.write_text("synthetic test input\n")
            output = root / "results"

            fitted = {
                "status": "EXPERIMENTAL_FIT_NOT_APPROVED",
                "production_approval": False,
                "parlay_gate_modified": False,
            }
            bundle = {
                "artifact_status": "EXPERIMENTAL_NOT_APPROVED",
                "report": dict(fitted),
            }
            predictions = [{
                "event_id": "synthetic-event",
                "home_won": 1,
            }]

            def save_test_artifact(value, path):
                Path(path).write_bytes(b"synthetic artifact bytes")

            argv = [
                "train_moneyline_model.py",
                "--dataset", str(dataset),
                "--output-dir", str(output),
            ]

            with (
                patch("sys.argv", argv),
                patch.object(writer, "read_dataset", return_value=[{}]),
                patch.object(
                    writer,
                    "fit_experiment",
                    return_value=(fitted, bundle, predictions),
                ),
                patch("joblib.dump", side_effect=save_test_artifact),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = writer.main()

            self.assertEqual(result, 0)
            reports = list(output.glob("trainer_report_*.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            artifact = output / report["experimental_artifact_name"]

            self.assertEqual(
                report["experimental_artifact_sha256"],
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                report["dataset_sha256"],
                hashlib.sha256(dataset.read_bytes()).hexdigest(),
            )
            self.assertIs(report["production_approval"], False)
            self.assertIs(report["parlay_gate_modified"], False)

    def test_refused_training_has_no_artifact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset.csv"
            dataset.write_text("synthetic test input\n")
            output = root / "results"

            argv = [
                "train_moneyline_model.py",
                "--dataset", str(dataset),
                "--output-dir", str(output),
            ]

            with (
                patch("sys.argv", argv),
                patch.object(
                    writer,
                    "read_dataset",
                    side_effect=writer.TrainingRefused(
                        "INSUFFICIENT_SETTLED_DATA"
                    ),
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                writer.main()

            reports = list(output.glob("trainer_report_*.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertIsNone(report["experimental_artifact_name"])
            self.assertIsNone(report["experimental_artifact_sha256"])
            self.assertIs(report["production_approval"], False)
            self.assertFalse(list(output.glob("*.joblib")))


if __name__ == "__main__":
    unittest.main()
