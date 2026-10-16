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
    except (TypeError, ValueError) as exc:
        raise ThermalRiskFeatureError(f"invalid {name}: {value!r}") from exc
    if not math.isfinite(number):
        raise ThermalRiskFeatureError(f"non-finite {name}: {value!r}")
    return number


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    """Tetens-style saturation vapor pressure approximation in kPa."""
    temp_c = float(temp_c)
    return 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))


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

    actual_vapor_pressure = saturation_vapor_pressure_kpa(ambient) * (rh / 100.0)
    ambient_vpd = max(0.0, saturation_vapor_pressure_kpa(ambient) - actual_vapor_pressure)
    leaf_vpd = max(0.0, saturation_vapor_pressure_kpa(leaf) - actual_vapor_pressure)

    leaf_minus_reference = None if reference is None else leaf - reference
    thermal_abs_reference_delta = (
        None if leaf_minus_reference is None else abs(leaf_minus_reference)
    )

    return ThermalRiskFeatures(
        leaf_temp_c=leaf,
        ambient_temp_c=ambient,
        ambient_rh_pct=rh,
        reference_temp_c=reference,
        light_level=light,
        leaf_minus_ambient_c=leaf - ambient,
        leaf_minus_reference_c=leaf_minus_reference,
        ambient_vpd_kpa=ambient_vpd,
        leaf_vpd_kpa=leaf_vpd,
        leaf_air_vpd_delta_kpa=leaf_vpd - ambient_vpd,
        thermal_abs_reference_delta_c=thermal_abs_reference_delta,
        rgb_mite_evidence=rgb,
    )


def risk_training_allowed(*, field_label_policy_frozen: bool, cohort_audited: bool) -> bool:
    """Hard gate: V1 model fitting must wait for field label/cohort evidence."""
    return bool(field_label_policy_frozen and cohort_audited)
