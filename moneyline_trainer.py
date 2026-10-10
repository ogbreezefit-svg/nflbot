"""Offline experimental models; never connects to the app database."""
import csv
import math
from collections import Counter
from datetime import datetime, timezone

FEATURE_FIELDS = (
    "home_minus_away_passing_yards_per_attempt",
    "home_minus_away_completion_percentage",
    "home_minus_away_rushing_yards_per_carry",
)
POLICY = {"train_min": 100, "calibration_min": 40, "test_min": 40,
          "min_each_class": 10}

class TrainingRefused(RuntimeError):
    def __init__(self, reason, details=None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}

def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid dataset timestamp") from None
    if result.tzinfo is None:
        raise ValueError("Dataset timestamps must include timezone")
    return result.astimezone(timezone.utc)

def read_dataset(path, now=None):
    now = now or datetime.now(timezone.utc)
    required = {"event_id", "observation_key", "captured_at", "kickoff_time",
                "settled_at", "baseline_home_share", "home_won",
                "feature_version", *FEATURE_FIELDS}
    rows, events = [], set()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Dataset headers do not match evaluator export")
        for raw in reader:
            event = raw["event_id"].strip()
            if not event or event in events:
                raise ValueError("Missing or duplicate event ID")
            events.add(event)
            captured, kickoff, settled = (
                stamp(raw[field]) for field in
                ("captured_at", "kickoff_time", "settled_at")
            )
            if not captured < kickoff < settled <= now:
                raise ValueError("Invalid evidence/outcome chronology")
            lead = (kickoff - captured).total_seconds() / 3600
            if not 1 <= lead <= 24:
                raise ValueError("Trainer requires the default 1–24 hour window")
            if raw["home_won"] not in ("0", "1"):
                raise ValueError("Invalid outcome label")
            probability = float(raw["baseline_home_share"])
            if not math.isfinite(probability) or not 0 < probability < 1:
                raise ValueError("Invalid market baseline")
            if raw["feature_version"] != "moneyline-research-v1":
                raise ValueError("Unsupported feature version")
            features = []
            for field in FEATURE_FIELDS:
                text = raw[field].strip()
                value = float(text) if text else None
                if value is not None and not math.isfinite(value):
                    raise ValueError("Nonfinite research feature")
                features.append(value)
            rows.append({"event_id": event,
                         "observation_key": raw["observation_key"],
                         "captured_at": captured, "kickoff_time": kickoff,
                         "settled_at": settled,
                         "label": int(raw["home_won"]),
                         "baseline": probability, "features": features})
    return rows

def chronological_plan(rows):
    minimum = sum(POLICY[key] for key in
                  ("train_min", "calibration_min", "test_min"))
    if len(rows) < minimum:
        raise TrainingRefused("INSUFFICIENT_SETTLED_DATA", {
            "settled_rows": len(rows),
            "minimum_total_before_time_purging": minimum})
    if len({row["event_id"] for row in rows}) != len(rows):
        raise TrainingRefused("DUPLICATE_EVENTS")
    ordered = sorted(rows, key=lambda row: (row["captured_at"], row["event_id"]))
    test_start = ordered[-POLICY["test_min"]]["captured_at"]
    calibration_start = ordered[-(POLICY["test_min"] +
                                POLICY["calibration_min"])]["captured_at"]
    if calibration_start >= test_start:
        raise TrainingRefused("INSUFFICIENT_DISTINCT_TIME_GROUPS")
    train_candidates = [r for r in ordered if r["captured_at"] < calibration_start]
    calibration_candidates = [r for r in ordered
                              if calibration_start <= r["captured_at"] < test_start]
    train = [r for r in train_candidates if r["settled_at"] < calibration_start]
    calibration = [r for r in calibration_candidates if r["settled_at"] < test_start]
    test = [r for r in ordered if r["captured_at"] >= test_start]
    details = {
        "train_rows": len(train), "calibration_rows": len(calibration),
        "test_rows": len(test),
        "training_labels_purged": len(train_candidates) - len(train),
        "calibration_labels_purged": len(calibration_candidates) - len(calibration),
        "calibration_cutoff": calibration_start.isoformat(),
        "test_cutoff": test_start.isoformat(),
    }
    for name, subset in (("train", train), ("calibration", calibration), ("test", test)):
        if len(subset) < POLICY[f"{name}_min"]:
            raise TrainingRefused("INSUFFICIENT_DATA_AFTER_TIME_PURGING", details)
        counts = Counter(r["label"] for r in subset)
        if min(counts.get(0, 0), counts.get(1, 0)) < POLICY["min_each_class"]:
            raise TrainingRefused("INSUFFICIENT_CLASS_COVERAGE", details)
    varied = False
    for i in range(len(FEATURE_FIELDS)):
        values = [r["features"][i] for r in train if r["features"][i] is not None]
        if values and max(values) - min(values) > 1e-9:
            varied = True
    if not varied:
        raise TrainingRefused("NO_USABLE_RESEARCH_VARIATION", details)
    return {"train": train, "calibration": calibration, "test": test,
            "details": details}

def metrics(rows, probabilities):
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("Invalid metric inputs")
    probabilities = [float(p) for p in probabilities]
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("Invalid model probabilities")
    epsilon = 1e-15
    clipped = [min(1-epsilon, max(epsilon, p)) for p in probabilities]
    n = len(rows)
    return {"games": n,
            "brier_score": math.fsum((p-r["label"])**2 for r, p in zip(rows, probabilities))/n,
            "log_loss": -math.fsum(r["label"]*math.log(p)+(1-r["label"])*math.log1p(-p)
                                  for r, p in zip(rows, clipped))/n}

def fit_experiment(rows):
    plan = chronological_plan(rows)
    try:
        import numpy as np
        import sklearn
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        raise TrainingRefused("OPTIONAL_TRAINING_DEPENDENCIES_MISSING", plan["details"])

    def matrix(subset, research):
        values = []
        for row in subset:
            p = row["baseline"]
            vector = [math.log(p)-math.log1p(-p)]
            if research:
                vector += [np.nan if x is None else x for x in row["features"]]
            values.append(vector)
        return np.asarray(values, dtype=float)

    predictions, models = {}, {}
    for name, research in (("market_only", False), ("market_plus_research", True)):
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(C=1.0, max_iter=2000, random_state=0)),
        ])
        estimator.fit(matrix(plan["train"], research),
                      [r["label"] for r in plan["train"]])
        calibration_scores = estimator.decision_function(
            matrix(plan["calibration"], research)).reshape(-1, 1)
        calibrator = LogisticRegression(C=1.0, max_iter=2000, random_state=0)
        calibrator.fit(calibration_scores, [r["label"] for r in plan["calibration"]])
        test_scores = estimator.decision_function(matrix(plan["test"], research)).reshape(-1, 1)
        probabilities = calibrator.predict_proba(test_scores)[:, 1]
        predictions[name] = [float(p) for p in probabilities]
        models[name] = {"estimator": estimator, "calibrator": calibrator,
                        "uses_research_features": research}

    raw = [r["baseline"] for r in plan["test"]]
    scores = {"raw_market": metrics(plan["test"], raw)}
    scores.update({name: metrics(plan["test"], p) for name, p in predictions.items()})
    report = {
        "status": "EXPERIMENTAL_FIT_NOT_APPROVED",
        "evaluation_kind": "retrospective_chronological_holdout",
        "split": plan["details"], "test_metrics": scores,
        "research_minus_market_only_brier": (
            scores["market_plus_research"]["brier_score"]-scores["market_only"]["brier_score"]),
        "production_approval": False, "parlay_gate_modified": False,
        "sklearn_version": sklearn.__version__,
    }
    test_predictions = [{
        "event_id": row["event_id"], "observation_key": row["observation_key"],
        "captured_at": row["captured_at"].isoformat(), "home_won": row["label"],
        "raw_market_share": row["baseline"],
        "market_only_probability": predictions["market_only"][i],
        "market_plus_research_probability": predictions["market_plus_research"][i],
    } for i, row in enumerate(plan["test"])]
    bundle = {"artifact_status": "EXPERIMENTAL_NOT_APPROVED", "models": models,
              "raw_research_features": list(FEATURE_FIELDS),
              "policy": dict(POLICY), "report": report}
    return report, bundle, test_predictions
