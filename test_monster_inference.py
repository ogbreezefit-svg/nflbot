import math
import unittest

from frozen_player_features import EXPANDED_FEATURE_FIELDS
from monster_inference import predict_experimental_moneyline


class FakeEstimator:
    def decision_function(self, rows):
        self.rows = rows
        return [0.25]


class FakeCalibrator:
    classes_ = [0, 1]

    def predict_proba(self, rows):
        self.rows = rows
        return [[0.3, 0.7]]


class MonsterInferenceTests(unittest.TestCase):
    def setUp(self):
        self.estimator = FakeEstimator()
        self.calibrator = FakeCalibrator()
        self.features = {
            field: 1.0 for field in EXPANDED_FEATURE_FIELDS
        }
        self.bundle = {
            "artifact_status": "EXPERIMENTAL_NOT_APPROVED",
            "raw_research_features": list(EXPANDED_FEATURE_FIELDS),
            "report": {"production_approval": False},
            "models": {
                "market_plus_research": {
                    "uses_research_features": True,
                    "estimator": self.estimator,
                    "calibrator": self.calibrator,
                }
            },
        }

    def predict(self):
        return predict_experimental_moneyline(
            self.bundle, 0.6, self.features
        )

    def test_prediction_keeps_approval_false(self):
        result = self.predict()
        self.assertAlmostEqual(result["home_probability"], 0.7)
        self.assertAlmostEqual(result["away_probability"], 0.3)
        self.assertFalse(result["prediction_approved"])
        self.assertFalse(result["research_qualified"])
        self.assertFalse(result["publication_approved"])

    def test_training_vector_order_and_logit(self):
        self.predict()
        vector = self.estimator.rows[0]
        self.assertAlmostEqual(vector[0], math.log(0.6 / 0.4))
        self.assertEqual(
            vector[1:],
            [self.features[field] for field in EXPANDED_FEATURE_FIELDS],
        )

    def test_missing_feature_is_nan_and_reported(self):
        field = EXPANDED_FEATURE_FIELDS[0]
        self.features[field] = None
        result = self.predict()
        self.assertTrue(math.isnan(self.estimator.rows[0][1]))
        self.assertEqual(result["missing_feature_fields"], [field])

    def test_missing_field_rejected(self):
        self.features.pop(EXPANDED_FEATURE_FIELDS[0])
        with self.assertRaises(ValueError):
            self.predict()

    def test_feature_order_mismatch_rejected(self):
        self.bundle["raw_research_features"] = []
        with self.assertRaises(ValueError):
            self.predict()

    def test_approval_change_rejected(self):
        self.bundle["report"]["production_approval"] = True
        with self.assertRaises(ValueError):
            self.predict()

    def test_nonfinite_feature_rejected(self):
        self.features[EXPANDED_FEATURE_FIELDS[0]] = float("inf")
        with self.assertRaises(ValueError):
            self.predict()

    def test_invalid_baseline_rejected(self):
        with self.assertRaises(ValueError):
            predict_experimental_moneyline(
                self.bundle, 1.0, self.features
            )


if __name__ == "__main__":
    unittest.main()
