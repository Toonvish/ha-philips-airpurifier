"""Tests for value converter helpers in const.py."""

from __future__ import annotations

from custom_components.philips_airpurifier.const import (
    _ac3420_water_tank_present,
    _humidification_enabled,
    _humidification_enabled_new2,
    _runtime_hours,
    _to_celsius_from_tenths,
    _water_level_value,
)


def test_to_celsius_from_tenths() -> None:
    """Numeric tenths are converted, non-numeric values fall back to 0.0."""
    assert _to_celsius_from_tenths(215, {}) == 21.5
    assert _to_celsius_from_tenths("n/a", {}) == 0.0


def test_water_level_value() -> None:
    """Water level honors error codes and rejects non-numeric values."""
    assert _water_level_value(50, {}) == 50
    assert _water_level_value(50, {"err": 49408}) == 0
    assert _water_level_value(50, {"err": 32768}) == 0
    assert _water_level_value("n/a", {}) == 0


def test_runtime_hours() -> None:
    """Runtime milliseconds convert to hours; None and junk return None."""
    assert _runtime_hours(3600000, {}) == 1.0
    assert _runtime_hours(None, {}) is None
    assert _runtime_hours("n/a", {}) is None


def test_humidification_enabled() -> None:
    """Gen1 humidification is on for the 'PH' function value only."""
    assert _humidification_enabled("PH") is True
    assert _humidification_enabled("P") is False


def test_humidification_enabled_new2() -> None:
    """Gen2 humidification is on for function value 4 only."""
    assert _humidification_enabled_new2(4) is True
    assert _humidification_enabled_new2(1) is False


def test_ac3420_water_tank_present() -> None:
    """AC3420 water tank state is derived from mode and level values."""
    assert _ac3420_water_tank_present({"D0310A": 16, "D03240": 0}) is True
    assert _ac3420_water_tank_present({"D0310A": 16, "D03240": 1}) is False
    assert _ac3420_water_tank_present({}) is False
    assert _ac3420_water_tank_present({"D0310A": "x", "D03240": "y"}) is False
