from __future__ import annotations

import math
import unittest

from ml.pest_risk.thermal_mite_risk_v001 import (
    ThermalRiskFeatureError,
    _finite,
    build_thermal_risk_features,
    risk_training_allowed,
    saturation_vapor_pressure_kpa,
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
        self.assertAlmostEqual(features.ambient_vpd_kpa, 1.267111087003)
        self.assertAlmostEqual(features.leaf_vpd_kpa, 1.083250846661)
        self.assertAlmostEqual(features.leaf_air_vpd_delta_kpa, -0.183860240341)
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

    def test_optional_inputs_and_zero_rgb_remain_neutral_feature_values(self):
        missing = build_thermal_risk_features(
            leaf_temp_c=24.0,
            ambient_temp_c=25.0,
            ambient_rh_pct=60.0,
        )
        zero_rgb = build_thermal_risk_features(
            leaf_temp_c=24.0,
            ambient_temp_c=25.0,
            ambient_rh_pct=60.0,
            rgb_mite_evidence=0.0,
        )

        self.assertIsNone(missing.reference_temp_c)
        self.assertIsNone(missing.light_level)
        self.assertIsNone(missing.leaf_minus_reference_c)
        self.assertIsNone(missing.thermal_abs_reference_delta_c)
        self.assertIsNone(missing.rgb_mite_evidence)
        self.assertEqual(zero_rgb.rgb_mite_evidence, 0.0)
        self.assertEqual(
            zero_rgb.thermal_direction_policy,
            "BIDIRECTIONAL_CONTEXT_DEPENDENT",
        )

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

    def test_saturation_vapor_pressure_rejects_non_finite_and_undefined_inputs(self):
        invalid_inputs = (
            float("nan"),
            float("inf"),
            float("-inf"),
            -237.3,
            -238.0,
        )
        for value in invalid_inputs:
            with self.subTest(value=value), self.assertRaises(ThermalRiskFeatureError):
                saturation_vapor_pressure_kpa(value)

    def test_feature_builder_rejects_non_finite_derived_values(self):
        leaf_temp_c = 1e307
        self.assertTrue(math.isfinite(saturation_vapor_pressure_kpa(leaf_temp_c)))

        with self.assertRaisesRegex(
            ThermalRiskFeatureError,
            "non-finite derived feature leaf_minus_reference_c",
        ):
            build_thermal_risk_features(
                leaf_temp_c=leaf_temp_c,
                ambient_temp_c=25.0,
                ambient_rh_pct=50.0,
                reference_temp_c=-1.75e308,
            )

    def test_numeric_conversion_overflow_uses_feature_error_contract(self):
        huge_integer = 10**400

        with self.subTest(path="helper"), self.assertRaises(ThermalRiskFeatureError):
            _finite("huge_value", huge_integer, required=True)
        with self.subTest(path="builder"), self.assertRaises(ThermalRiskFeatureError):
            build_thermal_risk_features(
                leaf_temp_c=huge_integer,
                ambient_temp_c=25.0,
                ambient_rh_pct=50.0,
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

    def test_training_gate_requires_actual_boolean_approvals(self):
        truthy_non_boole = (1, "true", "approved", [True])
        for value in truthy_non_boole:
            with self.subTest(field_label_policy_frozen=value):
                self.assertFalse(risk_training_allowed(
                    field_label_policy_frozen=value,
                    cohort_audited=True,
                ))
            with self.subTest(cohort_audited=value):
                self.assertFalse(risk_training_allowed(
                    field_label_policy_frozen=True,
                    cohort_audited=value,
                ))


if __name__ == "__main__":
    unittest.main()
