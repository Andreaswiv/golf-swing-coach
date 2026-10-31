"""Swing analysis: raw keypoints -> phases, 2D measurements and readable feedback.

Works only from the saved keypoints file, so it can be re-run with improved
logic without running the pose model again.
"""

from __future__ import annotations

import logging

from .club import build_club_series, measure_club
from .feedback import build_feedback
from .measurements import measure, timing_problem
from .phases import PHASE_ORDER, NoSwingFound, detect_phases
from .ratings import rate_measurements
from .series import POLYORDER, build_series, rejected_landmarks

SWING_ANALYSIS_VERSION = "swing-0.5"

log = logging.getLogger("cv.swing")


def analyse_swing(payload: dict) -> dict:
    """Analyse a ``golfcoach.keypoints.v1`` payload. Never raises: failures become a status and a note."""
    result: dict = {
        "version": SWING_ANALYSIS_VERSION,
        "status": "ok",
        "camera_angle": payload.get("camera_angle"),
        "mirrored_for_left_handed": payload.get("handedness") == "left",
        "smoothing": None,
        "phases": [],
        "measurements": [],
        "notes": [],
        "feedback": None,
        "club": {"tracked": False},
    }
    try:
        series = build_series(payload)
        result["smoothing"] = {"method": "savitzky_golay", "window_frames": series.window, "polyorder": POLYORDER}
        # Joints dropped as impossible, per frame, so the player can leave them out too.
        result["rejected_landmarks"] = rejected_landmarks(series)
        phases = detect_phases(series)
    except NoSwingFound as exc:
        result["status"] = "no_swing_found"
        result["notes"].append({"code": "no_swing_found", "message": str(exc)})
        return result
    except Exception as exc:  # noqa: BLE001 - analysis must never sink the whole job
        log.exception("Swing analysis failed")
        result["status"] = "error"
        result["notes"].append(
            {"code": "analysis_error", "message": f"The swing analysis failed: {type(exc).__name__}: {exc}"}
        )
        return result

    for name in PHASE_ORDER:
        event = phases.events.get(name)
        if event:
            result["phases"].append(
                {
                    "name": name,
                    "frame_index": event.frame,
                    "timestamp_s": round(float(series.t[event.frame]), 4),
                    "method": event.method,
                    "confidence": event.confidence,
                }
            )
    result["notes"].extend(phases.notes)
    if timing_problem(series, phases) == "speed_change":
        result["notes"].append(
            {
                "code": "speed_change_suspected",
                "message": (
                    "The backswing and downswing do not fit together as one continuous speed: the clip "
                    "probably speeds up or slows down during the swing (common in phone slow motion), so "
                    "the tempo is left out. Trim the clip to the slow part, or film at normal speed."
                ),
            }
        )
    try:
        angle = payload.get("camera_angle", "")
        result["measurements"] = [m.to_dict() for m in measure(series, phases, angle)]
        club = build_club_series(payload, series)
        if club is not None:
            club_measurements, result["club"] = measure_club(club, series, phases, angle)
            result["measurements"] += [m.to_dict() for m in club_measurements]
        result["feedback"] = build_feedback(result["measurements"], angle, result["notes"], result["club"])
        rate_measurements(result["measurements"], result["club"])
    except Exception as exc:  # noqa: BLE001 - keep the phases even if a measurement breaks
        log.exception("Swing measurements failed")
        result["status"] = "error"
        result["notes"].append(
            {"code": "analysis_error", "message": f"The measurements failed: {type(exc).__name__}: {exc}"}
        )
    return result
