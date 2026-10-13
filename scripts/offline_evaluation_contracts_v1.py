"""Fixed exposed-development endpoints, sampling and finite-output accounting."""

import json
import math
import os


def atomic_snapshot(path, value):
    payload = json.dumps(value, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def pairs_from_metadata(names, lengths, training):
    if len(names) != 4 or len(set(names)) != 4 or set(names) & set(training):
        raise ValueError("evaluation partition leakage")
    pairs = []
    for index, name in enumerate(names):
        other = names[(index + 1) % len(names)]
        for current in range(5, lengths[name] - 8, 6):
            for negative in (False, True):
                pairs.append(
                    dict(
                        trajectory=name,
                        current=current,
                        goal_trajectory=other if negative else name,
                        goal_time=min(current + 6, lengths[other] - 1) if negative else current + 6,
                        negative=negative,
                    )
                )
    if not pairs:
        raise ValueError("empty pair set")
    return pairs


def validate(cfg, admission):
    names = admission["splits"]["dev"] + admission["splits"]["test"]
    lengths = {
        x["id"]: x["processed_frames"] for x in admission["trajectories"] if x["id"] in names
    }
    if cfg["partitions"] != {"train": admission["splits"]["train"], "development": names}:
        raise ValueError("partition drift")
    if cfg["pairs"]["development"] != pairs_from_metadata(
        names, lengths, admission["splits"]["train"]
    ):
        raise ValueError("fixed pair drift")
    if cfg["evaluation"] != {
        "draws": {"gnm": 1, "nomad": 4},
        "seed_base": 20261011,
        "horizon": 5,
        "batch_size": 1,
        "warmups": 2,
        "wall_seconds_per_model": 1800,
    }:
        raise ValueError("sampling/budget drift")
    for model in ("gnm", "nomad"):
        roles = cfg["checkpoints"][model]
        if [x["seed"] for x in roles] != [None, 0, 11, 22] or roles[0]["role"] != "release":
            raise ValueError("checkpoint role order drift")


def draw_seed(pair_index, draw):
    if type(pair_index) is not int or type(draw) is not int or pair_index < 0 or not 0 <= draw < 4:
        raise ValueError("draw identity")
    return 20261011 + 4 * pair_index + draw


def measure(prediction, label, distance_prediction, distance_label, action_valid, spacing):
    if type(action_valid) is not bool or not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("metric contract")
    if len(prediction) < 5 or len(label) < 5:
        raise ValueError("physical horizon missing")
    values = [distance_prediction, distance_label] + [
        v for rows in (prediction, label) for row in rows for v in row
    ]
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in values
    ):
        return dict(
            valid=False, action_valid=action_valid, ADE_m=None, FDE_m=None, distance_MAE_steps=None
        )
    errors = [
        math.hypot(prediction[i][0] - label[i][0], prediction[i][1] - label[i][1]) * spacing
        for i in range(5)
    ]
    return dict(
        valid=True,
        action_valid=action_valid,
        ADE_m=sum(errors) / 5 if action_valid else None,
        FDE_m=errors[-1] if action_valid else None,
        distance_MAE_steps=abs(distance_prediction - distance_label),
    )


def latency(start, end):
    if not all(math.isfinite(x) for x in (start, end)) or end < start:
        raise ValueError("invalid synchronized interval")
    return (end - start) * 1000


def summarize(rows, cfg):
    """Check the entire fixed population, then equal-pair expected-error summaries."""
    roles = cfg["checkpoints"][cfg["model"]]
    expected = {}
    for role in roles:
        for index, pair in enumerate(cfg["pairs"]["development"]):
            for draw in range(cfg["evaluation"]["draws"][cfg["model"]]):
                expected[(role["role"], role["seed"], index, draw)] = (role, pair)
    observed = {}
    for row in rows:
        key = (row["role"]["role"], row["role"]["seed"], row["pair_index"], row["draw"])
        if key in observed or key not in expected or (row["role"], row["pair"]) != expected[key]:
            raise ValueError("duplicate/unexpected draw identity")
        observed[key] = row
    groups = {}
    for key, (_, pair) in expected.items():
        group = (key[0], key[1], pair["trajectory"], pair["negative"])
        groups.setdefault(group, []).append(key)
    result = []
    for (role, seed, trajectory, negative), keys in groups.items():
        attempted = [observed[k] for k in keys if k in observed]
        returned = [r for r in attempted if r.get("returned", False)]
        valid = [r for r in returned if r["metrics"]["valid"]]
        item = dict(
            role=role,
            seed=seed,
            trajectory=trajectory,
            negative=negative,
            expected_draws=len(keys),
            attempted_draws=len(attempted),
            returned_draws=len(returned),
            valid_draws=len(valid),
            missing_draws=len(keys) - len(attempted),
            invalid_attempts=len(attempted) - len(valid),
            invalid_rate=(len(attempted) - len(valid)) / len(attempted) if attempted else None,
        )
        for metric in ("ADE_m", "FDE_m", "distance_MAE_steps"):
            relevant = [] if negative and metric != "distance_MAE_steps" else keys
            pair_ids = sorted(set(k[2] for k in relevant))
            means = []
            for index in pair_ids:
                draw_keys = [k for k in relevant if k[2] == index]
                data = [
                    observed[k]["metrics"][metric]
                    for k in draw_keys
                    if k in observed
                    and observed[k].get("returned", False)
                    and observed[k]["metrics"]["valid"]
                ]
                if len(data) == len(draw_keys) and all(v is not None for v in data):
                    means.append(sum(data) / len(data))
            item[metric] = dict(
                mean=sum(means) / len(means) if means and len(means) == len(pair_ids) else None,
                eligible_pairs=len(pair_ids),
                complete_pairs=len(means),
            )
        item["latency_ms"] = [r["inference_ms"] for r in returned]
        result.append(item)
    return result


def invalid_output(action_valid, reason):
    return dict(
        valid=False,
        action_valid=action_valid,
        reason=reason,
        ADE_m=None,
        FDE_m=None,
        distance_MAE_steps=None,
    )


def output_metrics(predictions, distances, labels, distance_label, action_valid, spacing, horizon):
    if (
        not isinstance(predictions, list)
        or len(predictions) != 1
        or not isinstance(predictions[0], list)
        or len(predictions[0]) != horizon
        or any(not isinstance(row, list) or len(row) < 2 for row in predictions[0])
    ):
        return invalid_output(action_valid, "action shape")

    def flatten(value):
        if isinstance(value, list):
            return [x for part in value for x in flatten(part)]
        return [value]

    flat = flatten(distances)
    if len(flat) != 1:
        return invalid_output(action_valid, "distance cardinality")
    return measure(predictions[0], labels, flat[0], distance_label, action_valid, spacing)


def retained_attempt(report, identity, callback, persist):
    row = dict(identity, returned=False)
    report["rows"].append(row)
    persist()
    try:
        row.update(callback(), returned=True)
    except BaseException as exc:
        row.update(error_type=type(exc).__name__, stage="prediction_exception")
        raise
    finally:
        persist()
