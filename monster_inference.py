"""Experimental moneyline inference. No model loading, approval, or writes."""
import math
from collections.abc import Mapping

from frozen_player_features import EXPANDED_FEATURE_FIELDS


def finite_number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be numeric.") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def predict_experimental_moneyline(bundle, baseline_home_share, features):
    if not isinstance(bundle, Mapping):
        raise ValueError("Model bundle must be a mapping.")
    if bundle.get("artifact_status") != "EXPERIMENTAL_NOT_APPROVED":
        raise ValueError("Expected an explicitly experimental artifact.")

    expected = list(EXPANDED_FEATURE_FIELDS)
    if bundle.get("raw_research_features") != expected:
        raise ValueError("Artifact research feature order does not match code.")

    report = bundle.get("report")
    if not isinstance(report, Mapping):
        raise ValueError("Artifact evaluation report is missing.")
    if report.get("production_approval") is not False:
        raise ValueError("Unexpected experimental approval state.")

    models = bundle.get("models")
    if not isinstance(models, Mapping):
        raise ValueError("Artifact models are missing.")
    model = models.get("market_plus_research")
    if not isinstance(model, Mapping):
        raise ValueError("Research model is missing.")
    if model.get("uses_research_features") is not True:
        raise ValueError("Expected the research-feature model.")

    if not isinstance(features, Mapping):
        raise ValueError("Features must be a mapping.")
    if set(features) != set(expected):
        raise ValueError("Feature fields must exactly match training fields.")

    baseline = finite_number(baseline_home_share, "Baseline home share")
    if not 0 < baseline < 1:
        raise ValueError("Baseline home share must be in (0, 1).")

    vector = [math.log(baseline) - math.log1p(-baseline)]
    missing = []
    for field in expected:
        value = features[field]
        if value is None:
            vector.append(float("nan"))
            missing.append(field)
        else:
            vector.append(finite_number(value, field))

    estimator = model.get("estimator")
    calibrator = model.get("calibrator")
    if estimator is None or calibrator is None:
        raise ValueError("Estimator or calibrator is missing.")

    classes = list(calibrator.classes_)
    if len(classes) != 2 or set(classes) != {0, 1}:
        raise ValueError("Unexpected calibration classes.")

    scores = estimator.decision_function([vector])
    if len(scores) != 1:
        raise ValueError("Expected one estimator score.")
    score = finite_number(scores[0], "Estimator score")

    probabilities = calibrator.predict_proba([[score]])
    if len(probabilities) != 1 or len(probabilities[0]) != 2:
        raise ValueError("Unexpected probability output shape.")

    values = [
        finite_number(value, "Calibration probability")
        for value in probabilities[0]
    ]
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError("Calibration probabilities outside [0, 1].")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-8):
        raise ValueError("Calibration probabilities do not sum to one.")

    home = values[classes.index(1)]
    return {
        "status": "EXPERIMENTAL_PREDICTION",
        "home_probability": home,
        "away_probability": 1.0 - home,
        "missing_feature_fields": missing,
        "prediction_approved": False,
        "research_qualified": False,
        "publication_approved": False,
    }
