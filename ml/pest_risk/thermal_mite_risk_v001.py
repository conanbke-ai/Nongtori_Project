from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


class ThermalRiskFeatureError(ValueError):
    pass


@dataclass(frozen=True)
class ThermalRiskFeatures:
    leaf_temp_c: float
    ambient_temp_c: float
    ambient_rh_pct: float
    reference_temp_c: float | None
    light_level: float | None
    leaf_minus_ambient_c: float
    leaf_minus_reference_c: float | None
    ambient_vpd_kpa: float
    leaf_vpd_kpa: float
    leaf_air_vpd_delta_kpa: float
    thermal_abs_reference_delta_c: float | None
    rgb_mite_evidence: float | None
    thermal_direction_policy: str = "BIDIRECTIONAL_CONTEXT_DEPENDENT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(name: str, value: float | int | None, *, required: bool) -> float | None:
    if value is None:
        if required:
            raise ThermalRiskFeatureError(f"{name} is required")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ThermalRiskFeatureError(f"invalid {name}: {value!r}") from exc
    if not math.isfinite(number):
        raise ThermalRiskFeatureError(f"non-finite {name}: {value!r}")
    return number


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    """Tetens-style saturation vapor pressure approximation in kPa."""
    temperature = _finite("temp_c", temp_c, required=True)
    assert temperature is not None

    denominator = temperature + 237.3
    if denominator == 0.0:
        raise ThermalRiskFeatureError(
            "saturation vapor pressure is undefined for temp_c=-237.3"
        )

    try:
        pressure = 0.6108 * math.exp(
            (17.27 * temperature) / denominator
        )
    except (OverflowError, ZeroDivisionError) as exc:
        raise ThermalRiskFeatureError(
            f"cannot calculate saturation vapor pressure for temp_c={temperature!r}"
        ) from exc
    if not math.isfinite(pressure):
        raise ThermalRiskFeatureError(
            f"non-finite saturation vapor pressure for temp_c={temperature!r}"
        )
    return pressure


def build_thermal_risk_features(
    *,
    leaf_temp_c: float,
    ambient_temp_c: float,
    ambient_rh_pct: float,
    reference_temp_c: float | None = None,
    light_level: float | None = None,
    rgb_mite_evidence: float | None = None,
) -> ThermalRiskFeatures:
    leaf = _finite("leaf_temp_c", leaf_temp_c, required=True)
    ambient = _finite("ambient_temp_c", ambient_temp_c, required=True)
    rh = _finite("ambient_rh_pct", ambient_rh_pct, required=True)
    reference = _finite("reference_temp_c", reference_temp_c, required=False)
    light = _finite("light_level", light_level, required=False)
    rgb = _finite("rgb_mite_evidence", rgb_mite_evidence, required=False)

    assert leaf is not None and ambient is not None and rh is not None

    if not 0.0 <= rh <= 100.0:
        raise ThermalRiskFeatureError("ambient_rh_pct must be within [0, 100]")
    if rgb is not None and not 0.0 <= rgb <= 1.0:
        raise ThermalRiskFeatureError("rgb_mite_evidence must be within [0, 1]")

    ambient_saturation_vapor_pressure = saturation_vapor_pressure_kpa(ambient)
    leaf_saturation_vapor_pressure = saturation_vapor_pressure_kpa(leaf)
    actual_vapor_pressure = ambient_saturation_vapor_pressure * (rh / 100.0)
    ambient_vpd = max(
        0.0,
        ambient_saturation_vapor_pressure - actual_vapor_pressure,
    )
    leaf_vpd = max(
        0.0,
        leaf_saturation_vapor_pressure - actual_vapor_pressure,
    )

    leaf_minus_ambient = leaf - ambient
    leaf_minus_reference = None if reference is None else leaf - reference
    thermal_abs_reference_delta = (
        None if leaf_minus_reference is None else abs(leaf_minus_reference)
    )
    leaf_air_vpd_delta = leaf_vpd - ambient_vpd

    derived_values = {
        "leaf_minus_ambient_c": leaf_minus_ambient,
        "ambient_vpd_kpa": ambient_vpd,
        "leaf_vpd_kpa": leaf_vpd,
        "leaf_air_vpd_delta_kpa": leaf_air_vpd_delta,
    }
    if leaf_minus_reference is not None:
        derived_values["leaf_minus_reference_c"] = leaf_minus_reference
    if thermal_abs_reference_delta is not None:
        derived_values["thermal_abs_reference_delta_c"] = (
            thermal_abs_reference_delta
        )
    for name, value in derived_values.items():
        if not math.isfinite(value):
            raise ThermalRiskFeatureError(f"non-finite derived feature {name}")

    return ThermalRiskFeatures(
        leaf_temp_c=leaf,
        ambient_temp_c=ambient,
        ambient_rh_pct=rh,
        reference_temp_c=reference,
        light_level=light,
        leaf_minus_ambient_c=leaf_minus_ambient,
        leaf_minus_reference_c=leaf_minus_reference,
        ambient_vpd_kpa=ambient_vpd,
        leaf_vpd_kpa=leaf_vpd,
        leaf_air_vpd_delta_kpa=leaf_air_vpd_delta,
        thermal_abs_reference_delta_c=thermal_abs_reference_delta,
        rgb_mite_evidence=rgb,
    )


def risk_training_allowed(*, field_label_policy_frozen: bool, cohort_audited: bool) -> bool:
    """Hard gate: V1 model fitting must wait for field label/cohort evidence."""
    return field_label_policy_frozen is True and cohort_audited is True
