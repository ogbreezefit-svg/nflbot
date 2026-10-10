import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

import backend_research as backend


class BackendResearchTests(unittest.TestCase):
    def test_disabled_does_not_run(self):
        with patch.dict(os.environ, {"BACKEND_RESEARCH_ENABLED": "false"}):
            with patch.object(backend, "_run_locked") as run:
                backend.run_backend_research()
                run.assert_not_called()

    def test_export_train_persist_and_skip_unchanged(self):
        def fake_process(command, **kwargs):
            script = Path(command[1]).name
            output = Path(command[command.index("--output-dir") + 1])
            output.mkdir(parents=True, exist_ok=True)

            if script == "evaluate_moneyline_research.py":
                (output / "moneyline_dataset_test.csv").write_text("event_id\n")
                (output / "moneyline_evaluation_test.json").write_text(
                    json.dumps({"database_dialect": "postgresql"})
                )
            elif script == "train_moneyline_model.py":
                dataset = Path(command[command.index("--dataset") + 1])
                self.assertTrue(dataset.exists())
                (output / "trainer_report_test.json").write_text(json.dumps({
                    "generated_at": "2026-10-10T23:00:00+00:00",
                    "status": "NOT_FITTED",
                    "reason": "INSUFFICIENT_SETTLED_DATA",
                    "settled_rows": 0,
                    "production_approval": False,
                    "parlay_gate_modified": False,
                }))
            else:
                self.fail(f"Unexpected script: {script}")

            return CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "BACKEND_RESEARCH_ENABLED": "true",
                "BACKEND_RESEARCH_DIR": directory,
            }):
                with patch.object(
                    backend.subprocess, "run", side_effect=fake_process
                ) as process:
                    backend.run_backend_research()
                    self.assertEqual(process.call_count, 2)

                    state_path = Path(directory) / "research_state.json"
                    self.assertTrue(state_path.exists())
                    state = json.loads(state_path.read_text())
                    self.assertFalse(state["production_approval"])
                    self.assertTrue((Path(directory) / state["report"]).exists())

                    backend.run_backend_research()
                    self.assertEqual(process.call_count, 3)


if __name__ == "__main__":
    unittest.main()
