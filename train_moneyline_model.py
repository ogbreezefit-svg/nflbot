"""Train from an evaluator CSV only. No app imports, APIs, or database access."""
from moneyline_trainer import FEATURE_FIELDS
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from moneyline_trainer import POLICY, TrainingRefused, read_dataset, fit_experiment

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset")
    parser.add_argument("--output-dir", default="local_backups/model_evaluation")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")
    report = {"generated_at": now.isoformat(), "status": "NOT_FITTED",
              "production_approval": False, "parlay_gate_modified": False,
              "minimum_sample_policy": dict(POLICY),
              "predictors": ["market_baseline_logit", *FEATURE_FIELDS],
              "limitations": [
                  "Minimum sample floors are implementation policy, not evidence of reliability.",
                  "Player/news predictors are observed proxies, not verified availability or current-role signals.",
                  "News variables count observed limited-feed mentions; publication times are unknown.",
                  "One fixed chronological holdout is not production validation.",
                  "No ticket construction, profitability claim, or automatic approval."]}
    bundle = None
    predictions = None
    try:
        if args.dataset:
            dataset = Path(args.dataset)
        else:
            candidates = list(Path("local_backups/evaluation").glob("moneyline_dataset_*.csv"))
            if not candidates:
                raise TrainingRefused("DATASET_NOT_FOUND")
            dataset = max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))
        report["dataset_name"] = dataset.name
        report["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
        rows = read_dataset(dataset, now=now)
        report["settled_rows"] = len(rows)
        fitted, bundle, predictions = fit_experiment(rows)
        report.update(fitted)
    except TrainingRefused as exc:
        report["reason"] = exc.reason
        report["refusal_details"] = exc.details
    except (OSError, ValueError) as exc:
        report["reason"] = "INVALID_OR_UNREADABLE_DATASET"
        report["error_class"] = type(exc).__name__

    # Remove an older approval-like artifact path from consideration by using unique names.
    if bundle is not None:
        import joblib
        bundle["dataset_sha256"] = report["dataset_sha256"]
        artifact = output / f"experimental_moneyline_{stamp}.joblib"
        joblib.dump(bundle, artifact)
        report["experimental_artifact_name"] = artifact.name
        with (output / f"retrospective_predictions_{stamp}.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
            writer.writeheader()
            writer.writerows(predictions)
    else:
        report["experimental_artifact_name"] = None

    (output / f"trainer_report_{stamp}.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    print("No database access, API calls, or parlay-gate changes.")
    return 0 if report.get("reason") != "INVALID_OR_UNREADABLE_DATASET" else 2

if __name__ == "__main__":
    raise SystemExit(main())
