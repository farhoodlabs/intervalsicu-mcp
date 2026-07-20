"""
Formatting utilities for Intervals.icu MCP Server

This module contains formatting functions for handling data from the Intervals.icu API.
"""

import json
from datetime import datetime
from typing import Any


class _KeyTracker(dict):
    """A dict wrapper that records which keys are accessed."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.accessed: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        self.accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.accessed.add(key)
        return super().__contains__(key)


def format_activity_summary(activity: dict[str, Any]) -> str:
    """Format an activity into a readable string."""
    start_time = activity.get("startTime", activity.get("start_date", "Unknown"))

    if isinstance(start_time, str) and len(start_time) > 10:
        # Format datetime if it's a full ISO string
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            start_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    rpe = activity.get("perceived_exertion", None)
    if rpe is None:
        rpe = activity.get("icu_rpe", "N/A")
    if isinstance(rpe, (int, float)):
        rpe = f"{rpe}/10"

    feel = activity.get("feel", "N/A")
    if isinstance(feel, int):
        feel = f"{feel}/5"

    # Gear (bike, shoes) - ICU activity payloads include the gear ID but not the
    # gear name (which lives in /athlete/{id}/gear). The tools.gear module
    # resolves the name and injects it as `_resolved_gear_name` before this
    # formatter runs. Prefer the resolved name; otherwise fall back to whatever
    # the raw payload provides (typically just an ID).
    resolved_name = activity.get("_resolved_gear_name")
    gear_raw = activity.get("gear")
    if resolved_name:
        gear_name = resolved_name
        if isinstance(gear_raw, dict):
            gear_id = gear_raw.get("id", activity.get("gear_id", "N/A"))
        else:
            gear_id = activity.get("gear_id", "N/A")
    elif isinstance(gear_raw, dict):
        gear_name = gear_raw.get("name") or gear_raw.get("display_name") or "N/A"
        gear_id = gear_raw.get("id", "N/A")
    else:
        gear_name = activity.get("gear_name", "N/A")
        gear_id = activity.get("gear_id", "N/A")

    return f"""
Activity: {activity.get("name", "Unnamed")}
ID: {activity.get("id", "N/A")}
Type: {activity.get("type", "Unknown")}
Date: {start_time}
Description: {activity.get("description", "N/A")}
Distance: {activity.get("distance", 0)} meters
Duration: {activity.get("duration", activity.get("elapsed_time", 0))} seconds
Moving Time: {activity.get("moving_time", "N/A")} seconds
Elevation Gain: {activity.get("elevationGain", activity.get("total_elevation_gain", 0))} meters
Elevation Loss: {activity.get("total_elevation_loss", "N/A")} meters

Power Data:
Average Power: {activity.get("avgPower", activity.get("icu_average_watts", activity.get("average_watts", "N/A")))} watts
Weighted Avg Power: {activity.get("icu_weighted_avg_watts", "N/A")} watts
Training Load: {activity.get("trainingLoad", activity.get("icu_training_load", "N/A"))}
FTP: {activity.get("icu_ftp", "N/A")} watts
Kilojoules: {activity.get("icu_joules", "N/A")}
Intensity: {activity.get("icu_intensity", "N/A")}
Power:HR Ratio: {activity.get("icu_power_hr", "N/A")}
Variability Index: {activity.get("icu_variability_index", "N/A")}

Heart Rate Data:
Average Heart Rate: {activity.get("avgHr", activity.get("average_heartrate", "N/A"))} bpm
Max Heart Rate: {activity.get("max_heartrate", "N/A")} bpm
LTHR: {activity.get("lthr", "N/A")} bpm
Resting HR: {activity.get("icu_resting_hr", "N/A")} bpm
Decoupling: {activity.get("decoupling", "N/A")}

Other Metrics:
Cadence: {activity.get("average_cadence", "N/A")} rpm
Calories burned: {activity.get("calories", "N/A")} kcal
Average Speed: {activity.get("average_speed", "N/A")} m/s
Max Speed: {activity.get("max_speed", "N/A")} m/s
Average Stride: {activity.get("average_stride", "N/A")}
L/R Balance: {activity.get("avg_lr_balance", "N/A")}
Weight: {activity.get("icu_weight", "N/A")} kg
RPE: {rpe}
Session RPE: {activity.get("session_rpe", "N/A")}
Feel: {feel}

Environment:
Trainer: {activity.get("trainer", "N/A")}
Average Temp: {activity.get("average_temp", "N/A")}°C
Min Temp: {activity.get("min_temp", "N/A")}°C
Max Temp: {activity.get("max_temp", "N/A")}°C
Avg Wind Speed: {activity.get("average_wind_speed", "N/A")} km/h
Headwind %: {activity.get("headwind_percent", "N/A")}%
Tailwind %: {activity.get("tailwind_percent", "N/A")}%

Training Metrics:
Fitness (CTL): {activity.get("icu_ctl", "N/A")}
Fatigue (ATL): {activity.get("icu_atl", "N/A")}
TRIMP: {activity.get("trimp", "N/A")}
Polarization Index: {activity.get("polarization_index", "N/A")}
Power Load: {activity.get("power_load", "N/A")}
HR Load: {activity.get("hr_load", "N/A")}
Pace Load: {activity.get("pace_load", "N/A")}
Efficiency Factor: {activity.get("icu_efficiency_factor", "N/A")}

Device Info:
Device: {activity.get("device_name", "N/A")}
Power Meter: {activity.get("power_meter", "N/A")}
File Type: {activity.get("file_type", "N/A")}

Gear:
Name: {gear_name}
ID: {gear_id}
"""


def format_workout(workout: dict[str, Any]) -> str:
    """Format a workout into a readable string."""
    return f"""
Workout: {workout.get("name", "Unnamed")}
Description: {workout.get("description", "No description")}
Sport: {workout.get("sport", "Unknown")}
Duration: {workout.get("duration", 0)} seconds
TSS: {workout.get("tss", "N/A")}
Intervals: {len(workout.get("intervals", []))}
"""


def _format_training_metrics(entries: dict[str, Any]) -> list[str]:
    """Format training metrics section."""
    training_metrics = []
    for k, label in [
        ("ctl", "Fitness (CTL)"),
        ("atl", "Fatigue (ATL)"),
    ]:
        if entries.get(k) is not None:
            training_metrics.append(f"- {label}: {entries[k]}")

    # Form (a.k.a. TSB, Training Stress Balance) = CTL - ATL. Intervals.icu does
    # not return this on the wellness record, so compute it when both components
    # are present AND numeric. The isinstance guard keeps a non-numeric value from
    # raising out of the formatter and taking down the whole wellness render.
    # Positive = fresher/tapered, negative = carrying fatigue.
    ctl, atl = entries.get("ctl"), entries.get("atl")
    if isinstance(ctl, (int, float)) and isinstance(atl, (int, float)):
        training_metrics.append(f"- Form (TSB): {ctl - atl:.1f}")

    for k, label in [
        ("rampRate", "Ramp Rate"),
        ("ctlLoad", "CTL Load"),
        ("atlLoad", "ATL Load"),
    ]:
        if entries.get(k) is not None:
            training_metrics.append(f"- {label}: {entries[k]}")
    return training_metrics


def _format_sport_info(entries: dict[str, Any]) -> list[str]:
    """Format sport-specific info section."""
    sport_info_list = []
    if entries.get("sportInfo"):
        for sport in entries.get("sportInfo", []):
            if isinstance(sport, dict) and sport.get("eftp") is not None:
                sport_info_list.append(f"- {sport.get('type')}: eFTP = {sport['eftp']}")
    return sport_info_list


def _format_vital_signs(entries: dict[str, Any]) -> list[str]:
    """Format vital signs section."""
    vital_signs = []
    for k, label, unit in [
        ("weight", "Weight", "kg"),
        ("restingHR", "Resting HR", "bpm"),
        ("hrv", "HRV", ""),
        ("hrvSDNN", "HRV SDNN", ""),
        ("avgSleepingHR", "Average Sleeping HR", "bpm"),
        ("spO2", "SpO2", "%"),
        ("systolic", "Systolic BP", ""),
        ("diastolic", "Diastolic BP", ""),
        ("respiration", "Respiration", "breaths/min"),
        ("bloodGlucose", "Blood Glucose", "mmol/L"),
        ("lactate", "Lactate", "mmol/L"),
        ("vo2max", "VO2 Max", "ml/kg/min"),
        ("bodyFat", "Body Fat", "%"),
        ("abdomen", "Abdomen", "cm"),
        ("baevskySI", "Baevsky Stress Index", ""),
    ]:
        if entries.get(k) is not None:
            value = entries[k]
            if k == "systolic" and entries.get("diastolic") is not None:
                vital_signs.append(
                    f"- Blood Pressure: {entries['systolic']}/{entries['diastolic']} mmHg"
                )
            elif k not in ("systolic", "diastolic"):
                vital_signs.append(f"- {label}: {value}{(' ' + unit) if unit else ''}")
    return vital_signs


def _format_sleep_recovery(entries: dict[str, Any]) -> list[str]:
    """Format sleep and recovery section."""
    sleep_lines = []
    sleep_hours = None
    if entries.get("sleepSecs") is not None:
        sleep_hours = f"{entries['sleepSecs'] / 3600:.2f}"
    elif entries.get("sleepHours") is not None:
        sleep_hours = f"{entries['sleepHours']}"
    if sleep_hours is not None:
        sleep_lines.append(f"  Sleep: {sleep_hours} hours")

    if entries.get("sleepQuality") is not None:
        quality_value = entries["sleepQuality"]
        quality_labels = {1: "Great", 2: "Good", 3: "Average", 4: "Poor"}
        quality_text = quality_labels.get(quality_value, str(quality_value))
        sleep_lines.append(f"  Sleep Quality: {quality_value} ({quality_text})")

    if entries.get("sleepScore") is not None:
        sleep_lines.append(f"  Device Sleep Score: {entries['sleepScore']}/100")

    if entries.get("readiness") is not None:
        sleep_lines.append(f"  Readiness: {entries['readiness']}/10")

    return sleep_lines


def _format_menstrual_tracking(entries: dict[str, Any]) -> list[str]:
    """Format menstrual tracking section."""
    menstrual_lines = []
    if entries.get("menstrualPhase") is not None:
        menstrual_lines.append(f"  Menstrual Phase: {str(entries['menstrualPhase']).capitalize()}")
    if entries.get("menstrualPhasePredicted") is not None:
        menstrual_lines.append(
            f"  Predicted Phase: {str(entries['menstrualPhasePredicted']).capitalize()}"
        )
    return menstrual_lines


def _format_subjective_feelings(entries: dict[str, Any]) -> list[str]:
    """Format subjective feelings section."""
    subjective_lines = []
    for k, label in [
        ("soreness", "Soreness"),
        ("fatigue", "Fatigue"),
        ("stress", "Stress"),
        ("mood", "Mood"),
        ("motivation", "Motivation"),
        ("injury", "Injury Level"),
    ]:
        if entries.get(k) is not None:
            subjective_lines.append(f"  {label}: {entries[k]}/10")
    return subjective_lines


def _format_nutrition_hydration(entries: dict[str, Any]) -> list[str]:
    """Format nutrition and hydration section.

    Handles both legacy fields (kcalConsumed, hydrationVolume) and the native
    macro fields from the Intervals.icu API (carbohydrates, protein,
    fatTotal). All fields are rendered conditionally — a null/missing value
    hides the corresponding line for backward compatibility with older
    wellness records.
    """
    nutrition_lines = []
    for k, label, unit in [
        ("kcalConsumed", "Calories Consumed", ""),
        ("carbohydrates", "Carbohydrates", "g"),
        ("protein", "Protein", "g"),
        ("fatTotal", "Fat", "g"),
        ("hydrationVolume", "Hydration Volume", ""),
    ]:
        if entries.get(k) is not None:
            suffix = f" {unit}" if unit else ""
            nutrition_lines.append(f"- {label}: {entries[k]}{suffix}")

    if entries.get("hydration") is not None:
        nutrition_lines.append(f"  Hydration Score: {entries['hydration']}/10")

    return nutrition_lines


def _format_other_fields(entries: dict[str, Any], known_keys: set[str]) -> list[str]:
    """Format any fields not already handled by the standard formatting sections."""
    other_lines = []
    for key, value in entries.items():
        if key not in known_keys and value is not None:
            if isinstance(value, (dict, list)):
                other_lines.append(f"- {key}: {json.dumps(value)}")
            else:
                other_lines.append(f"- {key}: {value}")
    return other_lines


def format_wellness_entry(entries: dict[str, Any], include_all_fields: bool = False) -> str:
    """Format wellness entry data into a readable string.

    Formats various wellness metrics including training metrics, vital signs,
    sleep data, menstrual tracking, subjective feelings, nutrition, and activity.

    Args:
        entries: Dictionary containing wellness data fields such as:
            - Training metrics: ctl, atl, rampRate, ctlLoad, atlLoad
            - Vital signs: weight, restingHR, hrv, hrvSDNN, avgSleepingHR, spO2,
              systolic, diastolic, respiration, bloodGlucose, lactate, vo2max,
              bodyFat, abdomen, baevskySI
            - Sleep: sleepSecs, sleepHours, sleepQuality, sleepScore, readiness
            - Menstrual: menstrualPhase, menstrualPhasePredicted
            - Subjective: soreness, fatigue, stress, mood, motivation, injury
            - Nutrition: kcalConsumed, carbohydrates, protein, fatTotal, hydrationVolume, hydration
            - Activity: steps
            - Other: comments, locked, date
        include_all_fields: If True, any fields not covered by the standard
            sections are appended under an "Other Fields" heading (default False).

    Returns:
        A formatted string representation of the wellness entry.
    """
    if include_all_fields:
        entries = _KeyTracker(entries)
        # Mark metadata/internal keys so they don't appear in "Other Fields"
        entries.get("date")
        entries.get("updated")
        entries.get("tempWeight")
        entries.get("tempRestingHR")

    lines = ["Wellness Data:"]
    # The wellness record's own date lives in `id` (e.g. "2025-05-24"); some call
    # sites also inject an explicit `date`. Prefer `date`, fall back to `id`. Use
    # `or` chaining (not get-with-default) so a present-but-null `date` still falls
    # back rather than rendering "Date: None".
    lines.append(f"Date: {entries.get('date') or entries.get('id') or 'N/A'}")
    lines.append("")

    training_metrics = _format_training_metrics(entries)
    if training_metrics:
        lines.append("Training Metrics:")
        lines.extend(training_metrics)
        lines.append("")

    sport_info_list = _format_sport_info(entries)
    if sport_info_list:
        lines.append("Sport-Specific Info:")
        lines.extend(sport_info_list)
        lines.append("")

    vital_signs = _format_vital_signs(entries)
    if vital_signs:
        lines.append("Vital Signs:")
        lines.extend(vital_signs)
        lines.append("")

    sleep_lines = _format_sleep_recovery(entries)
    if sleep_lines:
        lines.append("Sleep & Recovery:")
        lines.extend(sleep_lines)
        lines.append("")

    menstrual_lines = _format_menstrual_tracking(entries)
    if menstrual_lines:
        lines.append("Menstrual Tracking:")
        lines.extend(menstrual_lines)
        lines.append("")

    subjective_lines = _format_subjective_feelings(entries)
    if subjective_lines:
        lines.append("Subjective Feelings:")
        lines.extend(subjective_lines)
        lines.append("")

    nutrition_lines = _format_nutrition_hydration(entries)
    if nutrition_lines:
        lines.append("Nutrition & Hydration:")
        lines.extend(nutrition_lines)
        lines.append("")

    if entries.get("steps") is not None:
        lines.append("Activity:")
        lines.append(f"- Steps: {entries['steps']}")
        lines.append("")

    if entries.get("comments"):
        lines.append(f"Comments: {entries['comments']}")
    if "locked" in entries:
        lines.append(f"Status: {'Locked' if entries.get('locked') else 'Unlocked'}")

    if include_all_fields and isinstance(entries, _KeyTracker):
        other_lines = _format_other_fields(entries, entries.accessed)
        if other_lines:
            lines.append("")
            lines.append("Other Fields:")
            lines.extend(other_lines)

    return "\n".join(lines)


def format_athlete_profile(athlete: dict[str, Any]) -> str:
    """Format an athlete profile into a readable string.

    Renders identity/physiology basics. The embedded per-sport settings blob is
    only summarised (a count) — get_sport_settings renders the detail.
    """
    name = athlete.get("name") or " ".join(
        p for p in [athlete.get("firstname"), athlete.get("lastname")] if p
    ) or "Unknown"
    lines = ["Athlete Profile:", "", f"Name: {name}", f"ID: {athlete.get('id', 'N/A')}"]

    weight = athlete.get("weight")
    if weight is None:
        weight = athlete.get("icu_weight")
    for label, value, unit in [
        ("Sex", athlete.get("sex"), ""),
        ("Date of Birth", athlete.get("icu_date_of_birth"), ""),
        ("Weight", weight, "kg"),
        ("Resting HR", athlete.get("icu_resting_hr"), "bpm"),
        ("Timezone", athlete.get("timezone"), ""),
        ("Units", athlete.get("measurement_preference"), ""),
    ]:
        if value is not None and value != "":
            lines.append(f"{label}: {value}{(' ' + unit) if unit else ''}")

    location = ", ".join(
        p for p in [athlete.get("city"), athlete.get("state"), athlete.get("country")] if p
    )
    if location:
        lines.append(f"Location: {location}")
    if athlete.get("icu_coach"):
        lines.append("Role: Coach")
    if athlete.get("bio"):
        lines.append(f"Bio: {athlete['bio']}")

    sport_settings = athlete.get("sportSettings") or athlete.get("icu_type_settings")
    if isinstance(sport_settings, list) and sport_settings:
        lines.append(
            f"Sport Settings: {len(sport_settings)} sport(s) configured "
            "(use get_sport_settings for FTP/zones/thresholds)"
        )
    return "\n".join(lines)


def _format_zone_line(label: str, zones: Any, names: Any, unit: str = "") -> str | None:
    """Render a zone-boundary array, pairing with names when they line up."""
    if not isinstance(zones, list) or not zones:
        return None
    if isinstance(names, list) and len(names) == len(zones):
        parts = [f"{n}: {z}{unit}" for n, z in zip(names, zones, strict=True)]
    else:
        parts = [f"{z}{unit}" for z in zones]
    return f"{label}: " + ", ".join(parts)


def format_sport_settings(settings: dict[str, Any]) -> str:
    """Format one per-sport settings record (FTP, zones, thresholds) into text.

    The record ``id`` is always shown — it is the identifier update_sport_settings
    needs to target a specific sport's settings.
    """
    types = settings.get("types") or []
    sport = ", ".join(str(t) for t in types) if types else "Unknown"
    lines = [f"Sport Settings — {sport}:", f"Settings ID: {settings.get('id', 'N/A')}"]

    power_bits = []
    for key, label, unit in [
        ("ftp", "FTP", "W"),
        ("indoor_ftp", "Indoor FTP", "W"),
        ("w_prime", "W'", "J"),
        ("p_max", "Pmax", "W"),
    ]:
        if settings.get(key) is not None:
            power_bits.append(f"{label}: {settings[key]}{unit}")
    if power_bits:
        lines += ["", "Power:"] + [f"- {b}" for b in power_bits]
        zone_line = _format_zone_line("Zones", settings.get("power_zones"), settings.get("power_zone_names"))
        if zone_line:
            lines.append(f"- {zone_line}")

    hr_bits = []
    for key, label in [("lthr", "LTHR"), ("max_hr", "Max HR")]:
        if settings.get(key) is not None:
            hr_bits.append(f"{label}: {settings[key]} bpm")
    if hr_bits:
        lines += ["", "Heart Rate:"] + [f"- {b}" for b in hr_bits]
        zone_line = _format_zone_line("Zones", settings.get("hr_zones"), settings.get("hr_zone_names"))
        if zone_line:
            lines.append(f"- {zone_line}")

    if settings.get("threshold_pace") is not None:
        units = settings.get("pace_units", "")
        lines += ["", "Pace:", f"- Threshold: {settings['threshold_pace']} {units}".rstrip()]
        zone_line = _format_zone_line("Zones", settings.get("pace_zones"), settings.get("pace_zone_names"))
        if zone_line:
            lines.append(f"- {zone_line}")

    defaults = []
    for key, label in [("warmup_time", "Warmup"), ("cooldown_time", "Cooldown")]:
        if settings.get(key) is not None:
            defaults.append(f"{label}: {settings[key]}s")
    if defaults:
        lines += ["", "Defaults: " + ", ".join(defaults)]
    return "\n".join(lines)


def format_athlete_summary(summary: dict[str, Any]) -> str:
    """Format a training-load summary (fitness/fatigue/form + totals) into text."""
    lines: list[str] = []
    if summary.get("date"):
        lines.append(f"Period ending {summary['date']}:")
    for key, label, unit in [
        ("count", "Activities", ""),
        ("moving_time", "Moving Time", "s"),
        ("distance", "Distance", "m"),
        ("total_elevation_gain", "Elevation Gain", "m"),
        ("training_load", "Training Load", ""),
        ("calories", "Calories", "kcal"),
        ("fitness", "Fitness (CTL)", ""),
        ("fatigue", "Fatigue (ATL)", ""),
        ("form", "Form (TSB)", ""),
        ("rampRate", "Ramp Rate", ""),
        ("eftp", "eFTP", "W"),
    ]:
        if summary.get(key) is not None:
            lines.append(f"- {label}: {summary[key]}{(' ' + unit) if unit else ''}")

    categories = summary.get("byCategory")
    if isinstance(categories, list) and categories:
        lines.append("By category:")
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            lines.append(
                f"  - {cat.get('category', '?')}: {cat.get('count', 0)} activities, "
                f"load {cat.get('training_load', 'N/A')}, {cat.get('moving_time', 'N/A')}s"
            )
    return "\n".join(lines) if lines else "No summary metrics available."


def format_event_summary(event: dict[str, Any]) -> str:
    """Format a basic event summary into a readable string."""

    # Update to check for "date" if "start_date_local" is not provided
    event_date = event.get("start_date_local", event.get("date", "Unknown"))
    event_type = "Workout" if event.get("workout") else "Race" if event.get("race") else "Other"
    event_name = event.get("name", "Unnamed")
    event_id = event.get("id", "N/A")
    event_desc = event.get("description", "No description")

    return f"""Date: {event_date}
ID: {event_id}
Type: {event_type}
Name: {event_name}
Description: {event_desc}"""


def format_event_details(event: dict[str, Any]) -> str:
    """Format detailed event information into a readable string."""

    event_details = f"""Event Details:

ID: {event.get("id", "N/A")}
Date: {event.get("date", "Unknown")}
Name: {event.get("name", "Unnamed")}
Description: {event.get("description", "No description")}"""

    # Check if it's a workout-based event
    if "workout" in event and event["workout"]:
        workout = event["workout"]
        event_details += f"""

Workout Information:
Workout ID: {workout.get("id", "N/A")}
Sport: {workout.get("sport", "Unknown")}
Duration: {workout.get("duration", 0)} seconds
TSS: {workout.get("tss", "N/A")}"""

        # Include interval count if available
        if "intervals" in workout and isinstance(workout["intervals"], list):
            event_details += f"""
Intervals: {len(workout["intervals"])}"""

    # Check if it's a race
    if event.get("race"):
        event_details += f"""

Race Information:
Priority: {event.get("priority", "N/A")}
Result: {event.get("result", "N/A")}"""

    # Include calendar information
    if "calendar" in event:
        cal = event["calendar"]
        event_details += f"""

Calendar: {cal.get("name", "N/A")}"""

    return event_details


def format_activity_message(message: dict[str, Any]) -> str:
    """Format an activity message/note into a readable string."""
    created = message.get("created", "Unknown")
    if isinstance(created, str) and len(created) > 10:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return f"""Author: {message.get("name", "Unknown")}
Date: {created}
Type: {message.get("type", "TEXT")}
Content: {message.get("content", "")}"""


def format_custom_item_details(item: dict[str, Any]) -> str:
    """Format detailed custom item information into a readable string."""
    lines = ["Custom Item Details:", ""]
    lines.append(f"ID: {item.get('id', 'N/A')}")
    lines.append(f"Name: {item.get('name', 'N/A')}")
    lines.append(f"Type: {item.get('type', 'N/A')}")

    if item.get("description"):
        lines.append(f"Description: {item['description']}")
    if item.get("visibility"):
        lines.append(f"Visibility: {item['visibility']}")
    if item.get("index") is not None:
        lines.append(f"Index: {item['index']}")
    if item.get("hide_script") is not None:
        lines.append(f"Hide Script: {item['hide_script']}")
    if item.get("content"):
        lines.append(f"Content: {json.dumps(item['content'], indent=2)}")

    return "\n".join(lines)


def format_intervals(intervals_data: dict[str, Any]) -> str:
    """Format intervals data into a readable string with all available fields.

    Args:
        intervals_data: The intervals data from the Intervals.icu API

    Returns:
        A formatted string representation of the intervals data
    """
    # Format basic intervals information
    result = f"""Intervals Analysis:

ID: {intervals_data.get("id", "N/A")}
Analyzed: {intervals_data.get("analyzed", "N/A")}

"""

    # Format individual intervals
    if "icu_intervals" in intervals_data and intervals_data["icu_intervals"]:
        result += "Individual Intervals:\n\n"

        for i, interval in enumerate(intervals_data["icu_intervals"], 1):
            result += f"""[{i}] {interval.get("label", f"Interval {i}")} ({interval.get("type", "Unknown")})
Duration: {interval.get("elapsed_time", 0)} seconds (moving: {interval.get("moving_time", 0)} seconds)
Distance: {interval.get("distance", 0)} meters
Start-End Indices: {interval.get("start_index", 0)}-{interval.get("end_index", 0)}

Power Metrics:
  Average Power: {interval.get("average_watts", 0)} watts ({interval.get("average_watts_kg", 0)} W/kg)
  Max Power: {interval.get("max_watts", 0)} watts ({interval.get("max_watts_kg", 0)} W/kg)
  Weighted Avg Power: {interval.get("weighted_average_watts", 0)} watts
  Intensity: {interval.get("intensity", 0)}
  Training Load: {interval.get("training_load", 0)}
  Joules: {interval.get("joules", 0)}
  Joules > FTP: {interval.get("joules_above_ftp", 0)}
  Power Zone: {interval.get("zone", "N/A")} ({interval.get("zone_min_watts", 0)}-{interval.get("zone_max_watts", 0)} watts)
  W' Balance: Start {interval.get("wbal_start", 0)}, End {interval.get("wbal_end", 0)}
  L/R Balance: {interval.get("avg_lr_balance", 0)}
  Variability: {interval.get("w5s_variability", 0)}
  Torque: Avg {interval.get("average_torque", 0)}, Min {interval.get("min_torque", 0)}, Max {interval.get("max_torque", 0)}

Heart Rate & Metabolic:
  Heart Rate: Avg {interval.get("average_heartrate", 0)}, Min {interval.get("min_heartrate", 0)}, Max {interval.get("max_heartrate", 0)} bpm
  Decoupling: {interval.get("decoupling", 0)}
  DFA α1: {interval.get("average_dfa_a1", 0)}
  Respiration: {interval.get("average_respiration", 0)} breaths/min
  EPOC: {interval.get("average_epoc", 0)}
  SmO2: {interval.get("average_smo2", 0)}% / {interval.get("average_smo2_2", 0)}%
  THb: {interval.get("average_thb", 0)} / {interval.get("average_thb_2", 0)}

Speed & Cadence:
  Speed: Avg {interval.get("average_speed", 0)}, Min {interval.get("min_speed", 0)}, Max {interval.get("max_speed", 0)} m/s
  GAP: {interval.get("gap", 0)} m/s
  Cadence: Avg {interval.get("average_cadence", 0)}, Min {interval.get("min_cadence", 0)}, Max {interval.get("max_cadence", 0)} rpm
  Stride: {interval.get("average_stride", 0)}

Elevation & Environment:
  Elevation Gain: {interval.get("total_elevation_gain", 0)} meters
  Altitude: Min {interval.get("min_altitude", 0)}, Max {interval.get("max_altitude", 0)} meters
  Gradient: {interval.get("average_gradient", 0)}%
  Temperature: {interval.get("average_temp", 0)}°C (Weather: {interval.get("average_weather_temp", 0)}°C, Feels like: {interval.get("average_feels_like", 0)}°C)
  Wind: Speed {interval.get("average_wind_speed", 0)} km/h, Gust {interval.get("average_wind_gust", 0)} km/h, Direction {interval.get("prevailing_wind_deg", 0)}°
  Headwind: {interval.get("headwind_percent", 0)}%, Tailwind: {interval.get("tailwind_percent", 0)}%

"""

    # Format interval groups
    if "icu_groups" in intervals_data and intervals_data["icu_groups"]:
        result += "Interval Groups:\n\n"

        for i, group in enumerate(intervals_data["icu_groups"], 1):
            result += f"""Group: {group.get("id", f"Group {i}")} (Contains {group.get("count", 0)} intervals)
Duration: {group.get("elapsed_time", 0)} seconds (moving: {group.get("moving_time", 0)} seconds)
Distance: {group.get("distance", 0)} meters
Start-End Indices: {group.get("start_index", 0)}-N/A

Power: Avg {group.get("average_watts", 0)} watts ({group.get("average_watts_kg", 0)} W/kg), Max {group.get("max_watts", 0)} watts
W. Avg Power: {group.get("weighted_average_watts", 0)} watts, Intensity: {group.get("intensity", 0)}
Heart Rate: Avg {group.get("average_heartrate", 0)}, Max {group.get("max_heartrate", 0)} bpm
Speed: Avg {group.get("average_speed", 0)}, Max {group.get("max_speed", 0)} m/s
Cadence: Avg {group.get("average_cadence", 0)}, Max {group.get("max_cadence", 0)} rpm

"""

    return result


def _format_duration_label(secs: int) -> str:
    """Format seconds into a concise human-readable label (e.g. 5s, 2m, 1h)."""
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        mins = secs // 60
        remainder = secs % 60
        if remainder:
            return f"{mins}m{remainder}s"
        return f"{mins}m"
    hours = secs // 3600
    remainder = (secs % 3600) // 60
    if remainder:
        return f"{hours}h{remainder}m"
    return f"{hours}h"


def format_power_curves(
    curves: list[dict[str, Any]],
    activity_type: str,
    include_normalised: bool,
) -> str:
    """Format extracted power curve data into a concise readable string.

    Args:
        curves: List of extracted curve data dicts with id, label, data_points.
        activity_type: The activity type used for the query.
        include_normalised: Whether W/kg data is included.

    Returns:
        A formatted string representation of the power curves.
    """
    lines: list[str] = [f"Power Curves ({activity_type}):", ""]

    for curve in curves:
        label = curve.get("label", curve.get("id", "Unknown"))
        start = curve.get("start", "")
        end = curve.get("end", "")
        date_range = ""
        if start and end:
            # Trim time portion if present
            start_short = start[:10] if len(start) > 10 else start
            end_short = end[:10] if len(end) > 10 else end
            date_range = f" ({start_short} to {end_short})"

        lines.append(f"{label}{date_range}:")

        data_points = curve.get("data_points", [])
        if not data_points:
            lines.append("  No data available for requested durations.")
            lines.append("")
            continue

        for point in data_points:
            dur_label = _format_duration_label(point["secs"])
            watts = point.get("watts")
            aid = point.get("activity_id", "")
            parts = [f"  {dur_label}: {watts}W"]
            if include_normalised and "watts_per_kg" in point:
                parts.append(f"{point['watts_per_kg']:.2f}W/kg")
                wkg_aid = point.get("wkg_activity_id", "")
                if wkg_aid and wkg_aid != aid:
                    parts.append(f"[{aid}|wkg:{wkg_aid}]")
                else:
                    parts.append(f"[{aid}]")
            else:
                parts.append(f"[{aid}]")
            lines.append(" ".join(parts))
        lines.append("")

    return "\n".join(lines)


def format_activity_search_results(results: list[dict[str, Any]]) -> str:
    """Format activity search hits into a compact one-line-per-result list."""
    lines = [f"Found {len(results)} activit{'y' if len(results) == 1 else 'ies'}:", ""]
    for r in results:
        date = r.get("start_date_local", "")
        if isinstance(date, str) and len(date) > 10:
            date = date[:10]
        extra = []
        if r.get("distance") is not None:
            extra.append(f"{r['distance']}m")
        if r.get("moving_time") is not None:
            extra.append(f"{r['moving_time']}s")
        if r.get("race"):
            extra.append("RACE")
        line = " | ".join([date or "?", str(r.get("type", "?")), str(r.get("name", "Unnamed"))])
        if extra:
            line += "  (" + ", ".join(extra) + ")"
        line += f"  [id: {r.get('id', 'N/A')}]"
        lines.append(line)
    return "\n".join(lines)


def format_best_efforts(efforts: list[dict[str, Any]], stream: str) -> str:
    """Format best-effort windows for a stream (power/hr/pace) into text."""
    lines = [f"Best Efforts ({stream}):", ""]
    for e in efforts:
        parts = []
        if e.get("duration") is not None:
            parts.append(_format_duration_label(int(e["duration"])))
        if e.get("distance") is not None:
            parts.append(f"{e['distance']}m")
        label = " / ".join(parts) if parts else "effort"
        idx = f"[idx {e.get('start_index', '?')}-{e.get('end_index', '?')}]"
        lines.append(f"- {label}: avg {e.get('average', 'N/A')}  {idx}")
    return "\n".join(lines)


def format_interval_stats(interval: dict[str, Any]) -> str:
    """Format a computed interval-stats block (a single Interval) into text."""
    lines = ["Interval Stats:", ""]
    for key, label, unit in [
        ("moving_time", "Moving Time", "s"),
        ("distance", "Distance", "m"),
        ("average_watts", "Avg Power", "W"),
        ("weighted_average_watts", "Weighted Avg Power", "W"),
        ("max_watts", "Max Power", "W"),
        ("average_watts_kg", "Avg Power", "W/kg"),
        ("intensity", "Intensity", ""),
        ("training_load", "Training Load", ""),
        ("joules", "Work", "J"),
        ("decoupling", "Decoupling", "%"),
        ("average_heartrate", "Avg HR", "bpm"),
        ("max_heartrate", "Max HR", "bpm"),
        ("average_cadence", "Avg Cadence", "rpm"),
        ("average_speed", "Avg Speed", "m/s"),
        ("gap", "GAP", "m/s"),
    ]:
        if interval.get(key) is not None:
            lines.append(f"- {label}: {interval[key]}{(' ' + unit) if unit else ''}")
    return "\n".join(lines)


def _format_step_intensity(step: dict[str, Any]) -> str:
    """Render a workout step's intensity target(s) from raw workout_doc JSON."""
    bits = []
    for key, label in [("power", ""), ("hr", "HR"), ("pace", "Pace"), ("cadence", "Cad")]:
        v = step.get(key)
        if not isinstance(v, dict):
            continue
        units = v.get("units", "")
        if v.get("start") is not None and v.get("end") is not None:
            val = f"{v['start']}-{v['end']}"
        elif v.get("value") is not None:
            val = f"{v['value']}"
        else:
            continue
        bits.append(f"{(label + ' ') if label else ''}{val}{units}")
    return ", ".join(bits)


def _format_workout_step(step: dict[str, Any], depth: int = 0) -> list[str]:
    """Recursively render one workout_doc step (handles repeat blocks). Depth-capped."""
    indent = "  " * (depth + 1)
    if depth > 6:
        return [f"{indent}- ...(nested too deep)"]
    reps = step.get("reps")
    substeps = step.get("steps")
    if reps and isinstance(substeps, list):
        lines = [f"{indent}{reps}x:"]
        for sub in substeps:
            if isinstance(sub, dict):
                lines.extend(_format_workout_step(sub, depth + 1))
        return lines
    parts = []
    if step.get("duration") is not None:
        parts.append(_format_duration_label(int(step["duration"])))
    if step.get("distance") is not None:
        parts.append(f"{step['distance']}m")
    tag = ""
    if step.get("warmup"):
        tag = " (warmup)"
    elif step.get("cooldown"):
        tag = " (cooldown)"
    elif step.get("freeride"):
        tag = " (free ride)"
    intensity = _format_step_intensity(step)
    if step.get("ramp") and intensity:
        intensity = "ramp " + intensity
    label = " ".join(parts) if parts else "step"
    detail = f" @ {intensity}" if intensity else ""
    text = step.get("text")
    return [f"{indent}- {label}{detail}{tag}{(' — ' + text) if text else ''}"]


def format_workout_summary(workout: dict[str, Any]) -> str:
    """Format one library workout as a compact one-line list entry."""
    line = " | ".join([str(workout.get("name", "Unnamed")), str(workout.get("type", "?"))])
    extra = []
    if workout.get("icu_training_load") is not None:
        extra.append(f"load {workout['icu_training_load']}")
    if workout.get("moving_time") is not None:
        extra.append(f"{workout['moving_time']}s")
    if workout.get("folder_id") is not None:
        extra.append(f"folder {workout['folder_id']}")
    if extra:
        line += "  (" + ", ".join(extra) + ")"
    return line + f"  [id: {workout.get('id', 'N/A')}]"


def format_workout_details(workout: dict[str, Any]) -> str:
    """Format a library workout in full, including its structured steps."""
    lines = [f"Workout: {workout.get('name', 'Unnamed')}", f"ID: {workout.get('id', 'N/A')}"]
    for key, label, unit in [
        ("type", "Type", ""),
        ("sub_type", "Sub-type", ""),
        ("indoor", "Indoor", ""),
        ("moving_time", "Duration", "s"),
        ("distance", "Distance", "m"),
        ("icu_training_load", "Training Load", ""),
        ("icu_intensity", "Intensity", ""),
        ("carbs_per_hour", "Carbs", "g/hr"),
        ("folder_id", "Folder", ""),
    ]:
        if workout.get(key) is not None:
            lines.append(f"{label}: {workout[key]}{(' ' + unit) if unit else ''}")
    if workout.get("description"):
        lines.append(f"Description: {workout['description']}")
    tags = workout.get("tags")
    if isinstance(tags, list) and tags:
        lines.append("Tags: " + ", ".join(str(t) for t in tags))

    doc = workout.get("workout_doc")
    if isinstance(doc, dict) and isinstance(doc.get("steps"), list) and doc["steps"]:
        lines += ["", "Steps:"]
        for step in doc["steps"]:
            if isinstance(step, dict):
                lines.extend(_format_workout_step(step))
    return "\n".join(lines)
