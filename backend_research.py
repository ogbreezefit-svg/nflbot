"""Scheduled experimental export/training. Never approves models or builds tickets."""
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("ogbreeze.backend_research")
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
log.propagate = False
APP_DIR = Path(__file__).resolve().parent


def enabled():
    return os.getenv("BACKEND_RESEARCH_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on"
    )


def run_backend_research():
    if not enabled():
        return

    configured = os.getenv("BACKEND_RESEARCH_DIR")
    if not configured:
        log.error("Backend research skipped: BACKEND_RESEARCH_DIR is missing.")
        return

    root = Path(configured)
    if not root.is_absolute() or not root.is_dir():
        log.error("Backend research skipped: configured storage directory is unavailable.")
        return

    try:
        with (root / "research.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log.info("Backend research skipped: another run holds the lock.")
                return

            _run_locked(root)
    except Exception as exc:
        log.error("Backend research failed: %s", type(exc).__name__)


def _run_locked(root):
    environment = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        environment[name] = "1"

    def execute(script, arguments):
        result = subprocess.run(
            [sys.executable, str(APP_DIR / script), *arguments],
            cwd=APP_DIR,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{script} exited with code {result.returncode}")

    state_path = root / "research_state.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}

    with tempfile.TemporaryDirectory(prefix="export_", dir=root) as directory:
        export_dir = Path(directory)
        execute("evaluate_moneyline_research.py", [
            "--output-dir", str(export_dir)
        ])

        datasets = list(export_dir.glob("moneyline_dataset_*.csv"))
        summaries = list(export_dir.glob("moneyline_evaluation_*.json"))
        if len(datasets) != 1 or len(summaries) != 1:
            raise ValueError("Expected exactly one dataset and evaluation summary")

        dataset = datasets[0]
        evaluation = json.loads(summaries[0].read_text())
        if evaluation.get("database_dialect") != "postgresql":
            raise ValueError("Backend training requires the configured PostgreSQL database")

        fingerprint = hashlib.sha256()
        fingerprint.update(dataset.read_bytes())
        for name in (
            "backend_research.py",
            "evaluate_moneyline_research.py",
            "moneyline_evaluation.py",
            "frozen_player_features.py",
            "train_moneyline_model.py",
            "moneyline_trainer.py",
            "requirements.txt",
        ):
            fingerprint.update((APP_DIR / name).read_bytes())
        signature = fingerprint.hexdigest()

        if previous.get("signature") == signature:
            log.info("Backend research: dataset and code unchanged; training skipped.")
            return

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_dir = root / "research_runs" / stamp
        run_dir.mkdir(parents=True, exist_ok=False)

        saved_dataset = run_dir / dataset.name
        saved_dataset.write_bytes(dataset.read_bytes())
        (run_dir / summaries[0].name).write_bytes(summaries[0].read_bytes())

        execute("train_moneyline_model.py", [
            "--dataset", str(saved_dataset),
            "--output-dir", str(run_dir),
        ])

        reports = list(run_dir.glob("trainer_report_*.json"))
        if len(reports) != 1:
            raise ValueError("Expected exactly one training report")

        report = json.loads(reports[0].read_text())
        if (
            report.get("production_approval") is not False
            or report.get("parlay_gate_modified") is not False
        ):
            raise ValueError("Unexpected approval or parlay-gate state")

        reason = report.get("reason")
        log.info(
            "Backend research: status=%s reason=%s settled_rows=%s",
            report.get("status"), reason, report.get("settled_rows"),
        )

        if reason in (
            "OPTIONAL_TRAINING_DEPENDENCIES_MISSING",
            "INVALID_OR_UNREADABLE_DATASET",
            "DATASET_NOT_FOUND",
        ):
            return

        state = {
            "signature": signature,
            "last_attempt_at": report["generated_at"],
            "status": report["status"],
            "reason": reason,
            "report": str(reports[0].relative_to(root)),
            "production_approval": False,
        }
        temporary = root / "research_state.tmp"
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(state_path)
