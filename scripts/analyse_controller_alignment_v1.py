"""Fixed offline timestamp alignment; no runtime stack or gain fitting."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

TOLERANCE_S = 1e-6
DT = 1 / 120
INPUT_SHA = "971cd8af171d8d522b069141539753b59d7d6ba66fea01f0df9fa2942b00a4d6"


def finite(values):
    if not all(
        isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in values
    ):
        raise ValueError("nonfinite or nonnumeric evidence")


def join(native, rows):
    """Ambiguous candidates are never selected; every input index is retained."""
    for n in native:
        finite([n["time"], n["controller_time"], *n["angular_velocity"]])
    for r in rows:
        finite([r["time"], r["evaluation_w"], r["evaluation_v"]])
    candidates = [
        [j for j, r in enumerate(rows) if abs(n["time"] - r["time"]) <= TOLERANCE_S] for n in native
    ]
    reverse = {j: [i for i, c in enumerate(candidates) if j in c] for j in range(len(rows))}
    matched = [
        (i, c[0]) for i, c in enumerate(candidates) if len(c) == 1 and len(reverse[c[0]]) == 1
    ]
    ni, ri = {i for i, _ in matched}, {j for _, j in matched}
    return {
        "pairs": matched,
        "native_unmatched": [i for i in range(len(native)) if i not in ni],
        "evaluation_unmatched": [j for j in range(len(rows)) if j not in ri],
        "ambiguous_native": [
            i for i, c in enumerate(candidates) if c and (len(c) != 1 or len(reverse[c[0]]) != 1)
        ],
        "candidate_indices": candidates,
        "ambiguous_evaluation": [
            j
            for j, ids in reverse.items()
            if ids and (len(ids) != 1 or len(candidates[ids[0]]) != 1)
        ],
        "exact_native_duplicate_group_count": len(duplicates([n["time"] for n in native])),
        "exact_evaluation_duplicate_group_count": len(duplicates([r["time"] for r in rows])),
        "exact_native_duplicates": duplicates([n["time"] for n in native]),
        "exact_evaluation_duplicates": duplicates([r["time"] for r in rows]),
    }


def duplicates(times):
    groups = {}
    for i, t in enumerate(times):
        groups.setdefault(t, []).append(i)
    return [ids for ids in groups.values() if len(ids) > 1]


def residual_stats(values):
    finite(values)
    return {
        "count": len(values),
        "signed_bias_rad_s": sum(values) / len(values) if values else None,
        "mae_rad_s": sum(abs(v) for v in values) / len(values) if values else None,
        "rms_rad_s": math.sqrt(sum(v * v for v in values) / len(values)) if values else None,
        "max_abs_rad_s": max(map(abs, values)) if values else None,
    }


def matched_window(records, lo, hi):
    subset = [r for r in records if lo <= r["evaluation_index"] < hi]
    return {
        "residual": residual_stats([r["gyro_minus_same_time_body_gt_rad_s"] for r in subset]),
        "matched_duration_s": DT * len(subset),
        "expected_ticks": hi - lo,
        "coverage": "complete" if len(subset) == hi - lo else "partial",
        "matched_only_gyro_integral_rad": DT * sum(r["native_gyro_rad_s"] for r in subset),
        "matched_only_gt_integral_rad": DT * sum(r["matched_gt_rad_s"] for r in subset),
    }


def describe(values):
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def window(rows):
    for r in rows:
        finite([*r["command"], r["control_output"], r["evaluation_v"], r["evaluation_w"]])
    return {
        "ticks": len(rows),
        "command_yaw_rad": DT * sum(r["command"][1] for r in rows),
        "achieved_yaw_rad": DT * sum(r["evaluation_w"] for r in rows),
        "command_distance_m": DT * sum(r["command"][0] for r in rows),
        "achieved_signed_distance_m": DT * sum(r["evaluation_v"] for r in rows),
        "pi_output_rad_s": describe([r["control_output"] for r in rows]),
    }


def segment(tick):
    return (tick - 120) // 60 if 120 <= tick < 1080 else None


def validate_frame(meta):
    if (
        meta["frame"] != "sensor/body-local"
        or meta["translation"] != [0, 0, 0]
        or meta["orientation_wxyz"] != [1, 0, 0, 0]
    ):
        raise ValueError("frame/mount mismatch")


def analyse(data):
    meta = data["imu_metadata"]
    validate_frame(meta)
    rows, native = data["rows"], data["imu_readings"]
    if len(rows) != 1200 or len(native) != 1080:
        raise ValueError("fixed evidence population mismatch")
    for i, r in enumerate(rows):
        if r["tick"] != i:
            raise ValueError("tick order mismatch")
        finite([r["time"], *r["evaluation_orientation_wxyz"], *r["evaluation_world_velocity"]])
        if i and abs(r["time"] - rows[i - 1]["time"] - DT) > TOLERANCE_S:
            raise ValueError("evaluation cadence mismatch")
    for n in native:
        if not n["valid"] or n["source"] != meta["source"] or len(n["angular_velocity"]) != 3:
            raise ValueError("native source/validity mismatch")
    for i, n in enumerate(native):
        if abs(n["controller_time"] - rows[i + 119]["time"]) > TOLERANCE_S:
            raise ValueError("consumption clock/source-index mismatch")
    alignment = join(native, rows)
    aligned = [
        {
            "native_index": i,
            "evaluation_index": j,
            "time_error_s": native[i]["time"] - rows[j]["time"],
            "acquisition_time_s": native[i]["time"],
            "controller_time_s": native[i]["controller_time"],
            "matched_evaluation_time_s": rows[j]["time"],
            "native_gyro_rad_s": native[i]["angular_velocity"][2],
            "matched_gt_rad_s": rows[j]["evaluation_w"],
            "consumption_pi_output_rad_s": rows[i + 120]["control_output"],
            "gyro_minus_same_time_body_gt_rad_s": native[i]["angular_velocity"][2]
            - rows[j]["evaluation_w"],
            "evaluation_command": rows[j]["command"],
            "evaluation_pi_output": rows[j]["control_output"],
            "acquisition_tick": rows[j]["tick"],
            "acquisition_segment": segment(rows[j]["tick"]),
            "consumption_tick": i + 120,
            "consumption_segment": segment(i + 120),
            "consumption_command": rows[i + 120]["command"],
            "crosses_segment_boundary": segment(rows[j]["tick"]) != segment(i + 120),
        }
        for i, j in alignment["pairs"]
    ]
    holds = []
    for k in range(16):
        start = 120 + 60 * k
        part = rows[start : start + 60]
        holds.append(
            {
                "segment": k,
                "command": part[0]["command"],
                "full": window(part),
                "transition_first30": window(part[:30]),
                "settled_last30": window(part[30:]),
                "native_window_coverage": {
                    label: sum(lo <= x["evaluation_index"] < hi for x in aligned)
                    for label, lo, hi in [
                        ("full", start, start + 60),
                        ("transition_first30", start, start + 30),
                        ("settled_last30", start + 30, start + 60),
                    ]
                },
                "acquisition_windows": {
                    label: matched_window(aligned, lo, hi)
                    for label, lo, hi in [
                        ("full", start, start + 60),
                        ("transition_first30", start, start + 30),
                        ("settled_last30", start + 30, start + 60),
                    ]
                },
                "same_time_error": residual_stats(
                    [
                        x["gyro_minus_same_time_body_gt_rad_s"]
                        for x in aligned
                        if start <= x["evaluation_index"] < start + 60
                    ]
                ),
            }
        )
    return {
        "scope": "offline descriptive alignment, no causal identification or gate change",
        "tolerance_s": TOLERANCE_S,
        "alignment": alignment,
        "aligned_records": aligned,
        "aligned_error_rad_s": residual_stats(
            [x["gyro_minus_same_time_body_gt_rad_s"] for x in aligned]
        ),
        "original_control_vs_later_gt_rad_s": residual_stats(
            [n["angular_velocity"][2] - rows[i + 120]["evaluation_w"] for i, n in enumerate(native)]
        ),
        "cross_boundary_count": sum(x["crosses_segment_boundary"] for x in aligned),
        "holds": holds,
        "unrecorded": ["PI integral state", "actual wheel targets"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    payload = a.input.read_bytes()
    if hashlib.sha256(payload).hexdigest() != INPUT_SHA:
        raise ValueError("frozen input SHA mismatch")
    a.out.mkdir(parents=True, exist_ok=False)
    result = analyse(json.loads(payload))
    result["input_sha256"] = INPUT_SHA
    result["analysis_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (a.out / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
