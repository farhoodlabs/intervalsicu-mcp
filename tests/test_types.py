"""
Tests for the workout data model in intervals_mcp_server.utils.types.

These exercise the serialization logic that builds ``add_or_update_event`` payloads:
round-trips (to_dict/from_dict/to_json/from_json), enum conversion, the camelCase
API key mapping, recursive nested steps, and the human-readable ``__str__`` output.
A bug in any branch (wrong key, missed enum conversion, broken recursion) fails here.
"""

import json

import pytest

from intervals_mcp_server.utils.types import (
    HrTarget,
    Intensity,
    PaceUnits,
    SportSettings,
    Step,
    Value,
    ValueUnits,
    WorkoutDoc,
    WorkoutTarget,
    float_to_str,
)


# --------------------------------------------------------------------------- #
# float_to_str
# --------------------------------------------------------------------------- #
def test_float_to_str_drops_trailing_zero():
    assert float_to_str(95.0) == "95"
    assert float_to_str(1.5) == "1.5"
    assert float_to_str(0.0) == "0"


# --------------------------------------------------------------------------- #
# Value
# --------------------------------------------------------------------------- #
def test_value_to_dict_only_includes_set_fields():
    assert Value(value=200, units=ValueUnits.WATTS).to_dict() == {"value": 200, "units": "w"}
    # unset fields must be omitted, not serialized as null
    assert "start" not in Value(value=1).to_dict()


def test_value_roundtrip_dict_and_json():
    original = Value(start=65, end=85, units=ValueUnits.PERCENT_FTP, target=HrTarget.THREE_SECOND)
    assert Value.from_dict(original.to_dict()) == original
    assert Value.from_json(original.to_json()) == original


def test_value_from_dict_converts_enums():
    val = Value.from_dict({"value": 3, "units": "power_zone", "target": "lap"})
    assert val.units is ValueUnits.POWER_ZONE
    assert val.target is HrTarget.LAP


@pytest.mark.parametrize(
    "value,units,expected",
    [
        (95.0, ValueUnits.PERCENT_FTP, "95% ftp"),
        (200.0, ValueUnits.WATTS, "200W"),
        (3.0, ValueUnits.POWER_ZONE, "Z3 W"),
        (90.0, ValueUnits.CADENCE, "90rpm Cadence"),
        (150.0, ValueUnits.PERCENT_HR, "150% HR"),
    ],
)
def test_value_str_formats_by_unit(value, units, expected):
    assert str(Value(value=value, units=units)) == expected


def test_value_str_ramp_and_target():
    assert str(Value(start=65, end=85, units=ValueUnits.PERCENT_FTP)) == "65%-85% ftp"
    assert str(Value(value=150, target=HrTarget.LAP)) == "150 hr=lap"


# --------------------------------------------------------------------------- #
# Step
# --------------------------------------------------------------------------- #
def test_step_roundtrip_with_nested_steps_and_values():
    """Recursive round-trip: a repeat block containing a step with power/hr targets."""
    original = Step(
        reps=3,
        intensity=Intensity.INTERVAL,
        steps=[
            Step(
                duration=300,
                power=Value(value=250, units=ValueUnits.WATTS),
                hr=Value(start=150, end=165, units=ValueUnits.PERCENT_LTHR),
                cadence=Value(value=90, units=ValueUnits.CADENCE),
            ),
            Step(duration=60, freeride=True),
        ],
    )
    as_dict = original.to_dict()
    # nested steps must serialize recursively, and enums become their .value
    assert as_dict["intensity"] == "interval"
    assert as_dict["steps"][0]["power"] == {"value": 250, "units": "w"}
    assert isinstance(as_dict["steps"], list) and len(as_dict["steps"]) == 2
    # full round-trip preserves the structure
    assert Step.from_dict(as_dict) == original
    assert Step.from_json(original.to_json()) == original


def test_step_to_dict_omits_unset_and_serializes_resolved_fields():
    step = Step(duration=120, _power=Value(value=248, units=ValueUnits.WATTS), _distance=1000.0)
    data = step.to_dict()
    assert data == {"duration": 120, "_power": {"value": 248, "units": "w"}, "_distance": 1000.0}
    assert "hr" not in data


@pytest.mark.parametrize(
    "duration,expected",
    [
        (45, "45s"),
        (120, "2m"),
        (125, "2m5s"),
        (3720, "1h2m"),
    ],
)
def test_step_format_duration(duration, expected):
    assert Step(duration=duration)._format_duration() == expected  # noqa: SLF001


@pytest.mark.parametrize("distance,expected", [(500, "500mtr"), (1500, "1.5km"), (2000, "2km")])
def test_step_format_distance(distance, expected):
    assert Step(distance=distance)._format_distance() == expected  # noqa: SLF001


def test_step_str_warmup_and_targets():
    out = str(Step(warmup=True, duration=600, power=Value(value=150, units=ValueUnits.WATTS)))
    assert "Warmup" in out
    assert "- 10m" in out
    assert "150W" in out


def test_step_str_reps_block_renders_children():
    block = Step(reps=3, steps=[Step(duration=60, power=Value(value=100, units=ValueUnits.WATTS))])
    out = str(block)
    assert "3x" in out
    assert "100W" in out


def test_step_str_nested_reps_raises():
    """A repeat inside a repeat is unsupported and must raise, not silently mis-render."""
    with pytest.raises(ValueError, match="Nested steps not supported"):
        Step(reps=2)._to_str(nested=True)  # noqa: SLF001


# --------------------------------------------------------------------------- #
# SportSettings
# --------------------------------------------------------------------------- #
def test_sport_settings_roundtrip():
    assert SportSettings().to_dict() == {}
    assert SportSettings.from_dict({"anything": 1}) == SportSettings()
    assert SportSettings.from_json(SportSettings().to_json()) == SportSettings()


# --------------------------------------------------------------------------- #
# WorkoutDoc
# --------------------------------------------------------------------------- #
def test_workout_doc_uses_camelcase_api_keys():
    doc = WorkoutDoc(
        description="Threshold 3x10",
        sport_settings=SportSettings(),
        zone_times=[600, 300, 120],
        target=WorkoutTarget.POWER,
        pace_units=PaceUnits.MINS_KM,
        steps=[Step(duration=600, power=Value(value=240, units=ValueUnits.WATTS))],
    )
    data = doc.to_dict()
    # API expects camelCase for these two specifically
    assert "sportSettings" in data and "sport_settings" not in data
    assert "zoneTimes" in data and "zone_times" not in data
    assert data["target"] == "POWER"
    assert data["pace_units"] == "MINS_KM"
    assert data["steps"][0]["power"] == {"value": 240, "units": "w"}


def test_workout_doc_roundtrip_dict_and_json():
    doc = WorkoutDoc(
        description="desc",
        duration=1800,
        ftp=266,
        target=WorkoutTarget.AUTO,
        sport_settings=SportSettings(),
        steps=[Step(reps=2, steps=[Step(duration=300, hr=Value(value=160, units=ValueUnits.HR_ZONE))])],
        zone_times=[{"id": 1, "secs": 100}],  # zone_times can be objects, not just ints
        options={"pool_length": "25m"},
        locales=["en"],
    )
    assert WorkoutDoc.from_dict(doc.to_dict()) == doc
    assert WorkoutDoc.from_json(doc.to_json()) == doc


def test_workout_doc_from_dict_maps_camelcase_back():
    doc = WorkoutDoc.from_dict(
        {"description": "d", "sportSettings": {}, "zoneTimes": [1, 2], "target": "HR"}
    )
    assert doc.sport_settings == SportSettings()
    assert doc.zone_times == [1, 2]
    assert doc.target is WorkoutTarget.HR


def test_workout_doc_str_includes_description_and_steps():
    doc = WorkoutDoc(description="Endurance", steps=[Step(duration=3600, freeride=True)])
    out = str(doc)
    assert out.startswith("Endurance")
    assert "freeride" in out


def test_workout_doc_json_is_valid_and_minimal():
    """to_json must emit real JSON with only the set fields."""
    payload = json.loads(WorkoutDoc(description="x", ftp=250).to_json())
    assert payload == {"description": "x", "ftp": 250}


# --------------------------------------------------------------------------- #
# Exhaustive round-trips (exercise every optional-field branch in to/from_dict)
# --------------------------------------------------------------------------- #
def test_value_str_no_units():
    assert str(Value(value=42)) == "42"


def test_step_all_fields_roundtrip():
    step = Step(
        text="Main set",
        text_locale={"en": "Main set"},
        duration=600,
        distance=1000.0,
        until_lap_press=True,
        reps=4,
        warmup=True,
        cooldown=True,
        intensity=Intensity.INTERVAL,
        steps=[Step(duration=60, freeride=True)],
        ramp=True,
        freeride=False,
        maxeffort=True,
        power=Value(value=250, units=ValueUnits.WATTS),
        hr=Value(value=160, units=ValueUnits.PERCENT_HR),
        pace=Value(value=300, units=ValueUnits.MINS_KM),
        cadence=Value(value=90, units=ValueUnits.CADENCE),
        hidepower=True,
        _power=Value(value=248, units=ValueUnits.WATTS),
        _hr=Value(value=158, units=ValueUnits.PERCENT_HR),
        _pace=Value(value=298, units=ValueUnits.MINS_KM),
        _distance=995.0,
    )
    assert Step.from_dict(step.to_dict()) == step


def test_step_format_none_paths():
    assert Step()._format_duration() == ""  # noqa: SLF001
    assert Step()._format_distance() == ""  # noqa: SLF001


def test_step_str_distance_flags_and_text():
    out = str(
        Step(
            cooldown=True,
            distance=500,
            maxeffort=True,
            ramp=True,
            hidepower=True,
            intensity=Intensity.REST,
            hr=Value(value=140, units=ValueUnits.PERCENT_HR),
            pace=Value(value=300, units=ValueUnits.MINS_KM),
            cadence=Value(value=85, units=ValueUnits.CADENCE),
            text="hold steady",
        )
    )
    assert "Cooldown" in out
    assert "500mtr" in out
    assert "maxeffort" in out and "ramp" in out and "hidepower" in out
    assert "intensity=rest" in out
    assert "140% HR" in out
    assert "85rpm Cadence" in out
    assert "hold steady" in out


def test_workout_doc_all_fields_roundtrip():
    doc = WorkoutDoc(
        description="Full",
        description_locale={"en": "Full"},
        duration=3600,
        distance=40000.0,
        ftp=266,
        lthr=174,
        threshold_pace=4.2,
        pace_units=PaceUnits.MINS_MILE,
        sport_settings=SportSettings(),
        category="WORKOUT",
        target=WorkoutTarget.PACE,
        steps=[Step(duration=600, power=Value(value=240, units=ValueUnits.WATTS))],
        zone_times=[600, 300],
        options={"pool_length": "25m"},
        locales=["en", "es"],
    )
    assert WorkoutDoc.from_dict(doc.to_dict()) == doc
