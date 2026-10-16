from __future__ import annotations

import unittest

from ml.pest_risk.thermal_mite_risk_v001 import (
    ThermalRiskFeatureError,
    build_thermal_risk_features,
    risk_training_allowed,
)


class ThermalMiteRiskV001Tests(unittest.TestCase):
    def test_relative_temperature_and_vpd_features(self):
        features = build_thermal_risk_features(
            leaf_temp_c=24.0,
            ambient_temp_c=25.0,
            ambient_rh_pct=60.0,
            reference_temp_c=24.5,
            light_level=100.0,
            rgb_mite_evidence=0.7,
        )
        self.assertAlmostEqual(features.leaf_minus_ambient_c, -1.0)
        self.assertAlmostEqual(features.leaf_minus_reference_c, -0.5)
        self.assertAlmostEqual(features.thermal_abs_reference_delta_c, 0.5)
        self.assertGreater(features.ambient_vpd_kpa, 0.0)
        self.assertGreaterEqual(features.leaf_vpd_kpa, 0.0)
        self.assertEqual(features.thermal_direction_policy, "BIDIRECTIONAL_CONTEXT_DEPENDENT")

    def test_no_directional_risk_assumption_is_encoded(self):
        cool = build_thermal_risk_features(
            leaf_temp_c=24.0,
            ambient_temp_c=25.0,
            ambient_rh_pct=60.0,
        )
        warm = build_thermal_risk_features(
            leaf_temp_c=26.0,
            ambient_temp_c=25.0,
            ambient_rh_pct=60.0,
        )
        self.assertLess(cool.leaf_minus_ambient_c, 0.0)
        self.assertGreater(warm.leaf_minus_ambient_c, 0.0)
        self.assertEqual(cool.thermal_direction_policy, warm.thermal_direction_policy)

    def test_rejects_invalid_humidity_and_rgb_confidence(self):
        with self.assertRaises(ThermalRiskFeatureError):
            build_thermal_risk_features(
                leaf_temp_c=24.0,
                ambient_temp_c=25.0,
                ambient_rh_pct=120.0,
            )
        with self.assertRaises(ThermalRiskFeatureError):
            build_thermal_risk_features(
                leaf_temp_c=24.0,
                ambient_temp_c=25.0,
                ambient_rh_pct=60.0,
                rgb_mite_evidence=1.2,
            )

    def test_training_gate_requires_label_and_cohort_audit(self):
        self.assertFalse(risk_training_allowed(
            field_label_policy_frozen=False,
            cohort_audited=True,
        ))
        self.assertFalse(risk_training_allowed(
            field_label_policy_frozen=True,
            cohort_audited=False,
        ))
        self.assertTrue(risk_training_allowed(
            field_label_policy_frozen=True,
            cohort_audited=True,
        ))


if __name__ == "__main__":
    unittest.main()
