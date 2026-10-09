import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from navfm.collection import scene_layouts as sl

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "configs" / "splits" / "heldout_layouts_v1.json"


def generator():
    spec = importlib.util.spec_from_file_location(
        "make_heldout", ROOT / "scripts" / "make_heldout_layouts_v1.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_legacy_appearance_aliases_modulo_five():
    # The defect that motivates explicit layouts: index 20 recreates scene 0 up to origin.
    a = sl.legacy_boxes(0, 2.0, False)
    b = sl.legacy_boxes(20, 2.0, False)
    assert [x["color"] for x in a] == [x["color"] for x in b]
    assert sl.legacy_boxes(3, 2.3, True)[-1]["name"] == "DoorPartition2"


def test_route_clearance_detects_collision_and_ignores_floor_and_decals():
    boxes = [
        sl.box("Floor", (2, 0, -0.05), (8, 8, 0.1), (0, 0, 0)),
        sl.box("Decal", (1, 0, 1.0), (0.2, 0.2, 0.2), (0, 0, 0), False),
        sl.box("Block", (2, 0.5, 0.3), (0.4, 0.4, 0.6), (0, 0, 0)),
    ]
    clear, near = sl.route_clearance([[0, 0], [3, 0]], boxes)
    assert near == "Block" and clear == pytest.approx(0.3, abs=1e-6)
    through, _ = sl.route_clearance([[0, 0.5], [3, 0.5]], boxes)
    assert through == 0.0


def test_teacher_rollout_reaches_and_times_out():
    ok, steps, poses = sl.teacher_rollout([[0, 0], [2, 0]], 0.2, max_steps=200)
    assert ok and 100 < steps < 140 and poses[-1][0] == pytest.approx(1.88, abs=0.03)
    assert not sl.teacher_rollout([[0, 0], [2, 0]], 0.2, max_steps=50)[0]


def test_goal_view_sees_panel_ahead_and_plain_wall_otherwise():
    boxes = [
        sl.box("Floor", (2, 0, -0.05), (8, 8, 0.1), (0, 0, 0)),
        sl.box("EndWall", (5, 0, 1.4), (0.2, 4, 2.8), (0, 0, 0)),
        sl.box("Panel", (4.885, 0, 1.0), (0.03, 0.9, 1.2), (1, 0, 0), False),
    ]
    ahead = sl.goal_view((3.0, 0.0, 0.0), boxes)
    assert ahead[len(ahead) // 2] == "Panel"
    aside = sl.goal_view((3.0, 1.6, 0.0), boxes)
    assert "Panel" not in aside[len(aside) // 2 :]


def test_heldout_spec_reproduces_and_passes_its_checks():
    spec = json.loads(SPEC.read_text())
    m = generator()
    built = m.build()
    assert spec["sealed"] is True
    assert spec["scenes"] == built["scenes"] and spec["routes"] == built["routes"]
    assert spec["content_digest"] == sl.digest({"scenes": spec["scenes"], "routes": spec["routes"]})
    verification, failures = m.verify(built)
    assert failures == [] and verification == spec["verification"]


def test_verification_rejects_coincident_endpoints():
    # Negative control for red-team finding 1: endpoints closer than twice the radius.
    m = generator()
    built = m.build()
    for r in built["routes"][:2]:
        r["waypoints"][-1] = [2.9, 0.1]
        r["waypoints"][-2] = [2.2, 0.1]
    _, failures = m.verify(built)
    assert any("endpoints too close" in f for f in failures)


def test_heldout_is_disjoint_from_training_and_dev():
    spec = json.loads(SPEC.read_text())
    split = json.loads((ROOT / "configs" / "splits" / "arrival_split_v2.json").read_text())
    assert set(split["held_out"]["groups"]) == {s["group"] for s in spec["scenes"]}
    used = set(split["training"]["scene_indices"]) | {3, 4}
    assert not used & {s["scene_index"] for s in spec["scenes"]}
    legacy = [b for k in range(5) for b in sl.legacy_boxes(k, 2.0, True)]
    colours = {tuple(b["color"]) for b in legacy}
    for scene in spec["scenes"]:
        for b in scene["boxes"]:
            nearest = min(math.dist(b["color"], c) for c in colours)
            assert nearest >= 0.15, (scene["group"], b["name"], nearest)


def test_legacy_and_training_routes_are_not_sealed():
    expansion = json.loads((ROOT / "configs/collection/option1_expansion_25.json").read_text())
    from navfm.collection.demonstrations import route_specs

    assert sl.sealed_matches(route_specs() + expansion, ROOT) == []
    scenes = [{"scene_index": k, "boxes": sl.legacy_boxes(k, 2.0, True)} for k in range(10)]
    assert sl.sealed_matches([], ROOT, scenes) == []


def test_seal_catches_geometric_and_appearance_bypasses():
    spec = json.loads(SPEC.read_text())
    r = dict(spec["routes"][0], id="renamed", scene_index=99)
    r["waypoints"] = [[x + 0.001, y] for x, y in r["waypoints"]]
    assert any("geometry" in m for m in sl.sealed_matches([r], ROOT))
    scene = dict(spec["scenes"][0], scene_index=99)
    assert any("resembles" in m for m in sl.sealed_matches([], ROOT, [scene]))


def test_ledger_slots_roles_and_retry(tmp_path, monkeypatch):
    spec = json.loads(SPEC.read_text())
    ledger = tmp_path / "ledger"
    crashed = tmp_path / "crashed"
    crashed.mkdir()
    (crashed / "collection.json").write_text(json.dumps({"episodes": []}))
    claim = sl.claim_unseal_slot
    claim(ledger, spec, out=crashed, role="teacher_goal_traversal", routes=[])
    # A run that attempted no episode may be retried once.
    ran = tmp_path / "ran"
    ran.mkdir()
    (ran / "collection.json").write_text(json.dumps({"episodes": [{"id": "a_route_0"}]}))
    claim(ledger, spec, out=ran, role="teacher_goal_traversal", routes=[])
    with pytest.raises(ValueError, match="exhausted"):
        claim(ledger, spec, out=tmp_path / "x", role="teacher_goal_traversal", routes=[])
    with pytest.raises(ValueError, match="unknown"):
        claim(ledger, spec, out=tmp_path / "y", role="pilot", routes=[])
    with pytest.raises(ValueError, match="checkpoint presence"):
        claim(ledger, spec, out=tmp_path / "z", role="policy_episode_run", routes=[])
    with pytest.raises(ValueError, match="not declared"):
        claim(
            ledger,
            spec,
            out=tmp_path / "w",
            role="policy_episode_run",
            routes=[],
            checkpoint_sha256="0" * 64,
            repo=ROOT,
        )
    sealed = spec["routes"][:1]
    with pytest.raises(ValueError, match="pinned ledger"):
        sl.require_scoring_allowed(ran, sealed, ROOT, ledger)
    monkeypatch.setattr(sl, "LEDGER_DIR", str(ledger))
    with pytest.raises(ValueError, match="recorded unseal run"):
        sl.require_scoring_allowed(tmp_path / "other", sealed, ROOT, ledger)
    sl.require_scoring_allowed(ran, sealed, ROOT, ledger)


def test_goal_swap_and_own_goals_must_come_from_teacher_run(tmp_path):
    spec = json.loads(SPEC.read_text())
    routes = spec["routes"][:2]
    ledger = tmp_path / "ledger"
    teacher = tmp_path / "teacher"
    teacher.mkdir()
    (teacher / "collection.json").write_text(json.dumps({"episodes": [{"id": "a_route_0"}]}))
    sl.claim_unseal_slot(ledger, spec, out=teacher, role="teacher_goal_traversal", routes=[])
    goals = tmp_path / "goals"
    goals.mkdir()

    def write(mapping):
        (goals / "goal_source.json").write_text(
            json.dumps(
                {
                    "goals": {
                        r: {"source": str(teacher / s / "trajectory/9.jpg")}
                        for r, s in mapping.items()
                    }
                }
            )
        )

    write({"a_route_0": "a_route_0", "a_route_1": "a_route_1"})
    sl.check_heldout_goals(goals, routes, "policy_episode_run", ledger)
    with pytest.raises(ValueError, match="teacher run of a_route_1"):
        sl.check_heldout_goals(goals, routes, "goal_swap_control", ledger)
    write({"a_route_0": "a_route_1", "a_route_1": "a_route_0"})
    sl.check_heldout_goals(goals, routes, "goal_swap_control", ledger)


def test_admission_rejects_heldout_split():
    from navfm.collection.dataset_admission import split_routes

    spec = json.loads(SPEC.read_text())
    with pytest.raises(ValueError, match="heldout"):
        split_routes(spec["routes"][:1])


def run_collector(tmp_path, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "collect_option1.py"),
            "--out",
            str(tmp_path / "run"),
            "--robot",
            "unused.usd",
            *map(str, extra),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_collector_refuses_sealed_spec_and_stripped_copies(tmp_path):
    proc = run_collector(tmp_path, "--layout-spec", SPEC)
    assert proc.returncode == 2 and "sealed held-out data refused" in proc.stderr
    spec = json.loads(SPEC.read_text())
    stripped = tmp_path / "copy.json"
    stripped.write_text(json.dumps({**spec, "sealed": False}))
    proc = run_collector(tmp_path / "a", "--layout-spec", stripped)
    assert proc.returncode == 2 and "sealed held-out data refused" in proc.stderr
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps([{**r, "id": "renamed"} for r in spec["routes"]]))
    proc = run_collector(tmp_path / "b", "--route-spec", routes)
    assert proc.returncode == 2 and "sealed held-out data refused" in proc.stderr
    proc = run_collector(tmp_path / "c", "--route-spec", SPEC)
    assert proc.returncode == 2 and "route list" in proc.stderr


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--limit", "10"], "every route"),
        (["--max-steps", "240"], "--max-steps 360"),
        (["--max-steps", "360", "--start-lateral-m", "0.3"], "perturbation"),
        (["--max-steps", "360", "--unseal-role", "pilot"], "--unseal-role must be"),
    ],
)
def test_unsealed_collection_is_bound_to_protocol(tmp_path, extra, message):
    proc = run_collector(
        tmp_path, "--layout-spec", SPEC, "--unseal-heldout", tmp_path / "ledger", *extra
    )
    assert proc.returncode == 2 and message in proc.stderr


def test_unseal_requires_pinned_ledger(tmp_path):
    proc = run_collector(
        tmp_path,
        "--layout-spec",
        SPEC,
        "--unseal-heldout",
        tmp_path / "ledger",
        "--max-steps",
        "360",
        "--unseal-role",
        "teacher_goal_traversal",
    )
    assert proc.returncode == 2 and "pinned ledger" in proc.stderr


def sealed_collection(tmp_path):
    tmp_path.mkdir()
    spec = json.loads(SPEC.read_text())
    (tmp_path / "frozen_routes.json").write_text(json.dumps(spec["routes"][:1]))
    (tmp_path / "collection.json").write_text(json.dumps({"status": "COMPLETED", "episodes": []}))
    return tmp_path


@pytest.mark.parametrize(
    "script, args",
    [
        ("admit_option1.py", ["--collection", "{c}", "--out", "{o}"]),
        (
            "score_teacher_replay.py",
            ["--collection", "{c}", "--out", "{o}", "--checkpoint", "{c}/x"],
        ),
        ("summarize_option1_live.py", ["--pretrained", "{c}", "--adapted", "{c}", "--out", "{o}"]),
    ],
)
def test_training_replay_and_summary_refuse_sealed(tmp_path, script, args):
    c = sealed_collection(tmp_path / "c")
    argv = [a.format(c=c, o=tmp_path / "out") for a in args]
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *argv],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 2, proc.stderr[-500:]
    assert "sealed held-out data refused" in proc.stderr


def test_scoring_scripts_refuse_sealed_routes(tmp_path):
    spec = json.loads(SPEC.read_text())
    (tmp_path / "frozen_routes.json").write_text(json.dumps(spec["routes"][:1]))
    (tmp_path / "collection.json").write_text(json.dumps({"episodes": []}))
    for script in ("audit_closed_loop_episodes.py", "decompose_live_episodes.py"):
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / script),
                "--collection",
                str(tmp_path),
                "--out",
                str(tmp_path / f"{script}.json"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 2 and "sealed held-out routes refused" in proc.stderr
