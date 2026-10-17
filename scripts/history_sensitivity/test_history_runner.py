"""Tests for history_runner.py. TEST mode only: a CPU model substitute, CUDA invisible.
No test loads the ViNT checkpoint or builds ViNT. The one production-mode launch
(test_production_preflight_without_cuda) runs with CUDA invisible and must abort NO_CUDA after
the read-only preflight and before any model construction.

Run (both environment variables are required; nothing is inferred):
  CUDA_VISIBLE_DEVICES= NAVFM_EVIDENCE_ROOT=<runtime-evidence root> HSR_MANIFEST=<path to
  history_call_manifest_v3.json> <isaac env python> -m pytest -q -p no:cacheprovider test_history_runner.py
"""
import json
import os
import shutil
import subprocess
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import history_runner as hr  # noqa: E402

_read_json, _read_text = hr._read_json, hr._read_text


def _write_text(path, text):
    with open(path, "w") as f:
        f.write(text)

RUNNER = os.path.join(HERE, "history_runner.py")
SUBS = os.path.join(HERE, "history_substitutes.py")
EVIDENCE_ROOT = os.environ["NAVFM_EVIDENCE_ROOT"]
MANIFEST = os.environ["HSR_MANIFEST"]
MANIFEST_SHA = hr.PINNED["manifest_sha256"]
ROOT = os.path.join(os.environ.get("HSR_TEST_OUTPUT_ROOT", HERE), "test_attempts")
assert os.environ.get("CUDA_VISIBLE_DEVICES") == "", "run the tests with CUDA_VISIBLE_DEVICES="
assert hr.sha_file(MANIFEST) == MANIFEST_SHA, "HSR_MANIFEST is not the pinned v3 manifest"
hr.EVIDENCE = EVIDENCE_ROOT


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_attempts():
    """Remove only the directory this test session created (marker-verified)."""
    created = not os.path.exists(ROOT)
    os.makedirs(ROOT, exist_ok=True)
    marker = os.path.join(ROOT, ".created-by-test-session")
    if created:
        _write_text(marker, str(os.getpid()))
    yield
    if created and os.path.exists(marker) and os.environ.get("HSR_KEEP_TEST_ATTEMPTS") != "1":
        for root, dirs, _ in os.walk(ROOT):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
        shutil.rmtree(ROOT)


def attempt_dir(name):
    os.makedirs(ROOT, exist_ok=True)
    return os.path.join(ROOT, f"{name}-{uuid.uuid4().hex[:8]}")


def run(*extra, manifest=MANIFEST, sha=MANIFEST_SHA, sub="Ok", test=True, attempt=None):
    attempt = attempt or attempt_dir(sub)
    cmd = [sys.executable, RUNNER, "run", "--manifest", manifest, "--manifest-sha256", sha,
           "--attempt-dir", attempt, "--evidence-root", EVIDENCE_ROOT]
    if test:
        cmd += ["--test-mode", "--backend", f"{SUBS}::{sub}"]
    p = subprocess.run(cmd + list(extra), capture_output=True, text=True, timeout=300)
    return p, attempt


def terminal(attempt, who):
    path = os.path.join(attempt, f"{who}_terminal.json")
    return _read_json(path) if os.path.exists(path) else None


def results(attempt):
    path = os.path.join(attempt, "results.jsonl")
    return _read_text(path).splitlines() if os.path.exists(path) else []


def tampered_manifest(edit):
    man = _read_json(MANIFEST)
    edit(man)
    path = attempt_dir("manifest") + ".json"
    with open(path, "w") as f:
        json.dump(man, f)
    return path, hr.sha_file(path)


def assert_no_model(attempt, reason):
    sup = terminal(attempt, "supervisor")
    assert sup["status"] == "ABORTED" and sup["reason"] == reason, sup
    assert not os.path.exists(os.path.join(attempt, "model_load.json"))
    assert results(attempt) == []
    assert hr.admit(attempt, accept_test=True)[0] is False


# --------------------------------------------------------------------------- normal completion
@pytest.fixture(scope="module")
def complete():
    p, attempt = run()
    assert p.returncode == 0, (p.stdout, p.stderr, terminal(attempt, "worker"))
    return attempt


@pytest.fixture(scope="module")
def complete_ordered():
    p, attempt = run(sub="OrderSensitive")
    assert p.returncode == 0, (p.stdout, p.stderr, terminal(attempt, "worker"))
    return attempt


def test_normal_completion(complete):
    sup, wt = terminal(complete, "supervisor"), terminal(complete, "worker")
    assert sup["status"] == "COMPLETE" and sup["retries"] == 0 and sup["mode"] == "TEST"
    assert sup["natural_exit"] is True and sup["forced_termination"] is False
    assert sup["session_members_killed_at_cleanup"] is False
    assert sup["execution_end_s"] <= sup["finalised_s"]
    assert "navfm.collection.rgb_baseline" in wt["module_origins_after_calls"]
    assert wt["forwards_listed"] == wt["forwards_hooked"] == 306
    lines = [json.loads(x) for x in results(complete)]
    assert [r["call_id"] for r in lines] == list(range(306))
    calls = _read_json(MANIFEST)["calls"]
    assert all(r["arm"] == c["arm"] and len(r["d_all"]) == len(c["batch_rows"])
               for r, c in zip(lines, calls, strict=True))
    load = _read_json(os.path.join(complete, "model_load.json"))
    assert load["forwards_during_load"] == 0 and load["device"] == "cpu"
    # deployed preprocessing and policy modules came from the staged, digest-matching snapshot
    assert {"navfm.collection.rgb_baseline", "navfm.upstream",
            "vint_train.data.data_utils"} <= set(load["module_origins"])
    env = _read_json(os.path.join(complete, "environment.json"))
    assert env["cuda_available"] is False and env["flags_isolated"] == 1


def test_admission_refuses_test_attempt_without_flag(complete):
    ok, reasons = hr.admit(complete)
    assert not ok and "TEST attempt" in reasons
    assert hr.admit(complete, accept_test=True) == (True, [])


def test_analysis_runs_on_admitted_attempt(complete):
    out = hr.analyse(complete, accept_test=True)
    ra = out["replay_agreement"]
    assert len(ra["per_query"]) == 72 and ra["gate_agreement"]["n"] == 72
    assert out["numerical"]["repeat_triples"] == 12 and out["numerical"]["repeats_bit_identical"]
    assert len(out["numerical"]["N_batch"]) == 12 and len(out["numerical"]["N_order"]) == 4
    pairs = out["arms"]["H2_posematched_other_variant"]["pairs"]
    assert len(pairs) == 34 and sum(p["mutual"] for p in pairs) == 16
    assert len(out["arms"]["H3_own_history_shifted5"]["per_call"]) == 72


def test_attempt_directory_is_consumed(complete):
    before = sorted(os.listdir(complete))
    p, _ = run(attempt=complete)
    assert p.returncode == 2 and "refusing" in p.stdout
    assert sorted(os.listdir(complete)) == before


# --------------------------------------------------------------------------- incomplete output
def _copy(src):
    dst = attempt_dir("copy")
    shutil.copytree(src, dst)
    return dst


def test_truncated_results_refused(complete):
    a = _copy(complete)
    lines = results(a)
    _write_text(os.path.join(a, "results.jsonl"), "\n".join(lines[:-1]) + "\n")
    ok, reasons = hr.admit(a, accept_test=True)
    assert not ok and any("305 results for 306" in r for r in reasons)


def test_altered_score_refused(complete):
    a = _copy(complete)
    lines = results(a)
    r = json.loads(lines[10])
    r["score"] += 1.0
    lines[10] = json.dumps(r, sort_keys=True)
    _write_text(os.path.join(a, "results.jsonl"), "\n".join(lines) + "\n")
    ok, reasons = hr.admit(a, accept_test=True)
    assert not ok and "results differ from the terminal digest" in reasons


def test_missing_supervisor_terminal_refused(complete):
    a = _copy(complete)
    os.remove(os.path.join(a, "supervisor_terminal.json"))
    assert hr.admit(a, accept_test=True)[0] is False


def test_analysis_refuses_unadmitted(complete):
    a = _copy(complete)
    os.remove(os.path.join(a, "model_load.json"))
    with pytest.raises(SystemExit):
        hr.analyse(a, accept_test=True)


# --------------------------------------------------------------------------- hash mismatches
def test_manifest_digest_mismatch():
    p, a = run(sha="0" * 64)
    assert p.returncode == 1
    assert_no_model(a, "HASH_MISMATCH")


def test_input_hash_differs_from_episode_record():
    def edit(m):
        c = next(c for c in m["calls"] if c["arm"] == "H3_own_history_shifted5")
        c["obs"][0]["sha256"] = "f" * 64
    path, sha = tampered_manifest(edit)
    _p, a = run(manifest=path, sha=sha)
    assert_no_model(a, "HASH_MISMATCH")


def test_file_bytes_verified(tmp_path):
    f = tmp_path / "x.jpg"
    f.write_bytes(b"abc")
    with pytest.raises(hr.Abort) as e:
        hr.read_verified({"path": str(f), "sha256": hr.sha_bytes(b"abd")})
    assert e.value.code == "HASH_MISMATCH"
    assert hr.read_verified({"path": str(f), "sha256": hr.sha_bytes(b"abc")}) == b"abc"


def test_source_snapshot_mismatch(tmp_path):
    good = b"x = 1\n"
    digest = hr.sha_bytes(good)
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / digest).write_bytes(b"x = 2\n")  # content no longer matches its address
    with pytest.raises(hr.Abort) as e:
        hr.stage_source({"/a/src/navfm/m.py": digest}, str(tmp_path / "staged"), snap=str(snap))
    assert e.value.code == "SOURCE_DIGEST"
    (snap / digest).chmod(0o644)
    (snap / digest).write_bytes(good)
    layout = hr.stage_source({"/a/src/navfm/m.py": digest}, str(tmp_path / "staged2"), snap=str(snap))
    assert next(iter(layout.values()))["sha256"] == digest


def test_deployed_assembly_check(complete, tmp_path):
    staged = os.path.join(complete, "staged_src")
    hr.check_assembly(staged)  # passes on the recorded source
    bad = tmp_path / "staged"
    shutil.copytree(staged, bad)
    p = bad / "navfm_src/navfm/collection/rgb_baseline.py"
    p.chmod(0o644)
    p.write_text(p.read_text().replace("obs = self.tensor(history).repeat(len(images), 1, 1, 1)",
                                       "obs = self.tensor(history[::-1]).repeat(len(images), 1, 1, 1)"))
    with pytest.raises(hr.Abort):
        hr.check_assembly(str(bad))


# --------------------------------------------------------------------------- malformed inputs
def test_call_order_malformed():
    def edit(m):
        m["calls"][0]["call_id"], m["calls"][1]["call_id"] = 1, 0
    path, sha = tampered_manifest(edit)
    _p, a = run(manifest=path, sha=sha)
    assert_no_model(a, "MALFORMED_INPUT")


def test_unreadable_manifest():
    path = attempt_dir("broken") + ".json"
    _write_text(path, '{"calls": [')
    _p, a = run(manifest=path, sha=hr.sha_file(path))
    assert_no_model(a, "MALFORMED_INPUT")


def test_query_image_change_breaks_pairing():
    def edit(m):
        c = next(c for c in m["calls"] if c["arm"] == "H1_repeated_static")
        other = next(x for x in m["calls"] if x["query_id"] != c["query_id"])
        c["obs"] = [other["obs"][-1]] * 6
    path, sha = tampered_manifest(edit)
    _p, a = run(manifest=path, sha=sha)
    assert_no_model(a, "PAIRING")


def test_reference_batch_change_breaks_pairing():
    def edit(m):
        c = next(c for c in m["calls"] if c["arm"] == "H2_posematched_other_variant")
        c["batch_rows"] = c["batch_rows"][1:]
        c["goal_row_index"] -= 1
    path, sha = tampered_manifest(edit)
    _p, a = run(manifest=path, sha=sha)
    assert_no_model(a, "PAIRING")


def test_production_population_pinned():
    man = _read_json(MANIFEST)
    man["calls"] = [c for c in man["calls"] if c["call_id"] != 305]
    with pytest.raises(hr.Abort) as e:
        hr.check_manifest(man, "PRODUCTION")
    assert e.value.code == "POPULATION"
    hr.check_manifest(_read_json(MANIFEST), "PRODUCTION")


def test_undecodable_image():
    with pytest.raises(hr.Abort) as e:
        hr.decode(b"not an image", "x.jpg")
    assert e.value.code == "MALFORMED_INPUT"


# --------------------------------------------------------------------------- caps and failures
def test_forward_budget_unit():
    b = hr.ForwardBudget(2)
    for _ in range(2):
        b.begin_listed()
        b.pre_hook(None, None)
        b.end_listed()
    with pytest.raises(hr.Abort) as e:
        b.begin_listed()
    assert e.value.code == "FORWARD_CAP"
    with pytest.raises(hr.Abort):
        hr.ForwardBudget(321)


def test_unlisted_forward_aborts():
    _p, a = run(sub="Unlisted")
    wt = terminal(a, "worker")
    assert terminal(a, "supervisor")["status"] == "ABORTED" and wt["reason"] == "UNLISTED_FORWARD"
    assert len(results(a)) == 2 and hr.admit(a, accept_test=True)[0] is False


def test_nonfinite_output_aborts():
    _p, a = run(sub="NaN")
    assert terminal(a, "worker")["reason"] == "OUTPUT_INVALID" and len(results(a)) == 1
    assert hr.admit(a, accept_test=True)[0] is False


def test_worker_failure_recorded_not_retried():
    _p, a = run(sub="Crash")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "WORKER_FAILED" and sup["worker_exit"] == 7 and sup["retries"] == 0
    assert terminal(a, "worker") is None and len(results(a)) == 2
    assert hr.admit(a, accept_test=True)[0] is False


def test_worker_self_limit_timeout():
    _p, a = run("--wall-limit-s", "90", sub="Slow")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "TIMEOUT" and sup["worker_exit"] == -14 and sup["forced_termination"] is False
    assert sup["execution_end_s"] < 90
    assert hr.admit(a, accept_test=True)[0] is False


def test_supervisor_deadline_kills_worker_group():
    _p, a = run("--wall-limit-s", "90", sub="SlowIgnoringAlarm")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "TIMEOUT" and sup["worker_exit"] == -9 and sup["forced_termination"] is True
    assert 90 <= sup["execution_end_s"] <= sup["finalised_s"]
    with pytest.raises(ProcessLookupError):
        os.killpg(sup["worker_pid"], 0)
    assert hr.admit(a, accept_test=True)[0] is False


def test_sampled_process_memory_guard():
    _p, a = run("--test-sampler-cmd", "echo {pid}, 5000", sub="Slow")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "MEMORY_CAP" and sup["gpu_process_peak_sampled_mib"] == 5000
    assert sup["gpu_process_samples_present"] >= 1
    assert hr.admit(a, accept_test=True)[0] is False


def test_memory_helpers():
    assert hr.parse_process_mib("123, 700\n456, 900\n123, 50\n", 123) == 750
    assert hr.parse_process_mib("", 1) == 0
    cap = hr.PINNED["gpu_allocator_cap_bytes"]
    assert hr.allocator_within_cap({"max_memory_reserved": cap, "max_memory_allocated": 1}, cap)
    assert not hr.allocator_within_cap({"max_memory_reserved": cap + 1, "max_memory_allocated": 1}, cap)


# --------------------------------------------------------------------------- production guards
def test_production_refuses_substitute_and_overrides():
    a = attempt_dir("prod")
    p = subprocess.run([sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256",
                        MANIFEST_SHA, "--attempt-dir", a, "--evidence-root", EVIDENCE_ROOT, "--backend", f"{SUBS}::Ok"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and not os.path.exists(a)
    assert "production mode accepts no backend, wall-limit or sampler override" in p.stdout
    p = subprocess.run([sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256",
                        "0" * 64, "--attempt-dir", a, "--evidence-root", EVIDENCE_ROOT],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and not os.path.exists(a)
    assert "production mode requires the pinned v3 manifest digest" in p.stdout
    p = subprocess.run([sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256",
                        MANIFEST_SHA, "--attempt-dir", a, "--evidence-root", EVIDENCE_ROOT, "--wall-limit-s", "5"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and not os.path.exists(a) and "overrides are test-only" in p.stdout


def test_test_mode_refuses_real_backend():
    a = attempt_dir("testvint")
    p = subprocess.run([sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256",
                        MANIFEST_SHA, "--attempt-dir", a, "--evidence-root", EVIDENCE_ROOT, "--test-mode"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and not os.path.exists(a) and "test mode requires a substitute backend" in p.stdout


def test_production_preflight_without_cuda():
    """Production preflight on the real inputs (hashes, pins, staging), then NO_CUDA abort."""
    _p, a = run(test=False)
    pre = _read_json(os.path.join(a, "preflight.json"))
    assert pre["status"] == "PASS" and pre["calls"] == 306
    assert pre["checkpoint_sha256"] == hr.PINNED["checkpoint_sha256"]
    wt = terminal(a, "worker")
    assert wt["reason"] == "NO_CUDA" and wt["stage"] == "environment" and wt["forwards_hooked"] == 0
    assert not os.path.exists(os.path.join(a, "model_load.json")) and results(a) == []


def test_supervisor_interrupt_kills_and_records():
    import signal
    import time

    a = attempt_dir("interrupt")
    proc = subprocess.Popen([sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256",
                             MANIFEST_SHA, "--attempt-dir", a, "--evidence-root", EVIDENCE_ROOT,
                             "--test-mode", "--backend", f"{SUBS}::Slow"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 120
    while not os.path.exists(os.path.join(a, "model_load.json")):
        assert time.monotonic() < deadline and proc.poll() is None
        time.sleep(0.5)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=60)
    sup = terminal(a, "supervisor")
    assert sup["status"] == "INTERRUPTED" and sup["execution_end_s"] <= sup["finalised_s"]
    with pytest.raises(ProcessLookupError):
        os.killpg(sup["worker_pid"], 0)
    assert hr.admit(a, accept_test=True)[0] is False


class _NotATensor:
    pass


def test_restricted_checkpoint_loading_refuses_pickled_objects(complete, tmp_path):
    """The deployed loader with trust_checkpoint=False (as the runner calls it) must refuse a
    checkpoint that needs unrestricted unpickling, rather than fall back to it."""
    import importlib.util

    import torch

    spec = importlib.util.spec_from_file_location(
        "staged_loader", os.path.join(complete, "staged_src/navfm_src/navfm/models/loader.py"))
    loader = importlib.util.module_from_spec(spec)
    sys.modules["staged_loader"] = loader  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(loader)
    finally:
        del sys.modules["staged_loader"]
    bad = tmp_path / "bad.pth"
    torch.save({"model": _NotATensor()}, bad)
    with pytest.raises(RuntimeError, match="not a plain state_dict"):
        loader.load_checkpoint(bad, trust_checkpoint=False, expected_sha256=hr.sha_file(bad))
    good = tmp_path / "good.pth"
    torch.save({"w": torch.zeros(2)}, good)
    assert loader.load_checkpoint(good, trust_checkpoint=False, expected_sha256=hr.sha_file(good))["w"].shape == (2,)


def test_relabelled_test_attempt_refused_and_count_pinned(complete):
    """Editing a CPU TEST attempt's own records to claim PRODUCTION must not make it admissible;
    and acceptance requires exactly the 306 pinned calls."""
    a = _copy(complete)
    plan = _read_json(os.path.join(a, "plan.json"))
    plan["mode"], plan["backend"] = "PRODUCTION", "vint"
    hr.write_json(os.path.join(a, "plan.json"), plan)
    ok, reasons = hr.admit(a)
    assert not ok and "mode or backend differs between plan and records" in reasons
    assert "production attempt did not run on CUDA" in reasons
    for name, edit in (("worker_terminal.json", {"mode": "PRODUCTION", "backend": "vint"}),
                       ("supervisor_terminal.json", {"mode": "PRODUCTION"}),
                       ("model_load.json", {"backend": "vint", "device": "cuda"}),
                       ("environment.json", {"cuda_available": True})):
        rec = _read_json(os.path.join(a, name))
        rec.update(edit)
        hr.write_json(os.path.join(a, name), rec)
    ok, reasons = hr.admit(a)
    assert not ok
    assert {"environment lacks a CUDA device record", "results lack CUDA allocator statistics",
            "ViNT and loader modules were not loaded from staged source",
            "the memory guard never observed the worker process"} <= set(reasons)
    path, sha = tampered_manifest(lambda m: m["calls"].pop())
    plan["manifest"], plan["manifest_sha256"] = path, sha
    hr.write_json(os.path.join(a, "plan.json"), plan)
    ok, reasons = hr.admit(a)
    assert not ok and any("exactly 306" in r for r in reasons)


def test_runner_loads_checkpoint_restricted():
    """The runner's own call site passes trust_checkpoint=False to the deployed loader."""
    import ast

    tree = ast.parse(_read_text(RUNNER))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "load_checkpoint"]
    assert len(calls) == 1
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(kw["trust_checkpoint"], ast.Constant) and kw["trust_checkpoint"].value is False
    assert "expected_sha256" in kw


def test_runner_assembly_bound_to_deployed(complete, tmp_path):
    staged = os.path.join(complete, "staged_src")
    hr.check_assembly(staged, runner_path=RUNNER)
    bad = tmp_path / "runner.py"
    bad.write_text(_read_text(RUNNER).replace("obs = tensor(history).repeat(len(images), 1, 1, 1)",
                                               "obs = tensor(history[::-1]).repeat(len(images), 1, 1, 1)"))
    with pytest.raises(hr.Abort):
        hr.check_assembly(staged, runner_path=str(bad))
    bad.write_text(_read_text(RUNNER).replace('for f in c["obs"]]', 'for f in c["obs"][::-1]]'))
    with pytest.raises(hr.Abort):
        hr.check_assembly(staged, runner_path=str(bad))
    bad.write_text(_read_text(RUNNER).replace("with torch.inference_mode():\n                    distance",
                                               "with torch.no_grad():\n                    distance"))
    with pytest.raises(hr.Abort):
        hr.check_assembly(staged, runner_path=str(bad))


def test_runner_matches_deployed_step_numerically(complete_ordered):
    """Drive the staged, deployed RGBTopomapBaseline.step on one recorded call with the same
    substitute model; its requested-goal row must equal the runner's logged d_all."""
    import importlib

    import numpy as np
    import torch

    complete = complete_ordered
    staged = os.path.join(complete, "staged_src")
    sys.path[:0] = [os.path.join(staged, "upstream_train"), os.path.join(staged, "navfm_src")]
    try:
        rgb = importlib.import_module("navfm.collection.rgb_baseline")
        dd = importlib.import_module("vint_train.data.data_utils")
        assert os.path.realpath(rgb.__file__).startswith(os.path.realpath(staged))
        import history_substitutes as subs

        man = _read_json(MANIFEST)
        call = man["calls"][0]
        query = next(q for q in man["queries"] if q["query_id"] == call["query_id"])
        rec = json.loads(results(complete)[0])
        arrays = [hr.decode(hr.read_verified(f), f["path"]) for f in call["obs"] + call["batch_rows"]]
        history, rows = arrays[:6], arrays[6:]
        eps = hr.load_episodes()
        config = eps[hr.EPISODES[0]]["policy"]["config"]
        captured = {}

        class Stop(Exception):
            pass

        class State:
            def window(self, cfg):
                return 0, len(rows) - 2

            def update(self, d, cfg):
                raise Stop

        class Recording(subs.OrderSensitive):
            def forward(self, obs, goals):
                out = super().forward(obs, goals)
                captured["d"] = np.asarray(out[0].numpy(), float).reshape(-1)
                return out

        pol = object.__new__(rgb.RGBTopomapBaseline)
        pol.torch, pol.device, pol.config = torch, "cpu", config
        pol.resize_and_aspect_crop, pol.model = dd.resize_and_aspect_crop, Recording().eval()
        pol.state, pol.topomap_cfg, pol.chain = State(), None, rows[:-1]
        pol.confirmation = pol.recovery = None
        assert query["window"][1] - query["window"][0] == len(rows) - 2
        with pytest.raises(Stop):
            pol.step(history, rows[-1])
        assert captured["d"].tolist() == rec["d_all"]
        # The comparison can fail: reordered history or reference rows change the output.
        with pytest.raises(Stop):
            pol.step(history[::-1], rows[-1])
        assert captured["d"].tolist() != rec["d_all"]
        pol.chain = rows[:-1][::-1]
        with pytest.raises(Stop):
            pol.step(history, rows[-1])
        assert captured["d"].tolist() != rec["d_all"]
    finally:
        del sys.path[:2]
        for name in [m for m in sys.modules if m == "navfm" or m.startswith(("navfm.", "vint_train"))]:
            del sys.modules[name]


def test_sampler_failures_do_not_kill_supervisor():
    _p, a = run("--test-sampler-cmd", "echo {pid}, [N/A]")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "COMPLETE" and sup["gpu_process_samples_failed"] >= 1
    assert sup["gpu_process_samples_present"] == 0


def test_hung_sampler_does_not_delay_completion():
    _p, a = run("--test-sampler-cmd", "sleep 30")
    sup = terminal(a, "supervisor")
    assert sup["status"] == "COMPLETE" and sup["gpu_process_samples_present"] == 0


def _synthetic():
    q = [dict(query_id="C_verify/junction_run_0000/k031", variant="C_verify", route="junction_run_0000", k=31, logged_requested_goal_distance=7.0,
              match=dict(other_variant="D_both", k=31)),
         dict(query_id="D_both/junction_run_0000/k031", variant="D_both", route="junction_run_0000", k=31, logged_requested_goal_distance=9.0,
              match=dict(other_variant="C_verify", k=31)),
         dict(query_id="D_both/junction_run_0000/k032", variant="D_both", route="junction_run_0000", k=32, logged_requested_goal_distance=8.0,
              match=dict(other_variant="C_verify", k=31))]
    ref = {"C_verify/junction_run_0000": {"median": 2.0}, "D_both/junction_run_0000": {"median": 0.5}}
    man = dict(queries=q, summary={"reference_scale_inregion_consecutive_abs_change": ref})
    sc = {("C_verify/junction_run_0000/k031", "H0_real", 0): 7.0, ("C_verify/junction_run_0000/k031", "H0_real", 1): 7.0,
          ("C_verify/junction_run_0000/k031", "H0_real", 2): 7.1,
          ("D_both/junction_run_0000/k031", "H0_real", 0): 9.5, ("D_both/junction_run_0000/k032", "H0_real", 0): 8.0,
          ("C_verify/junction_run_0000/k031", "H1_repeated_static", 0): 8.0,     # +1.0, accept -> reject
          ("D_both/junction_run_0000/k031", "H1_repeated_static", 0): 7.5,       # -2.0, reject -> accept
          ("D_both/junction_run_0000/k032", "H1_repeated_static", 0): 8.5,       # +0.5, no flip
          ("C_verify/junction_run_0000/k031", "H3_own_history_shifted5", 0): 7.0,
          ("D_both/junction_run_0000/k031", "H3_own_history_shifted5", 0): 9.5,
          ("D_both/junction_run_0000/k032", "H3_own_history_shifted5", 0): 8.0,
          ("C_verify/junction_run_0000/k031", "H2_posematched_other_variant", 0): 6.0,  # -1.0
          ("D_both/junction_run_0000/k031", "H2_posematched_other_variant", 0): 10.5,   # +1.0 (mutual with C k031)
          ("D_both/junction_run_0000/k032", "H2_posematched_other_variant", 0): 8.4,    # +0.4 (one direction)
          ("C_verify/junction_run_0000/k031", "CTRL_goal_only", 0): 7.25,
          ("C_verify/junction_run_0000/k031", "CTRL_reversed_node_rows", 0): 6.9}
    res = [dict(query_id=k, arm=a, repeat=r, score=v) for (k, a, r), v in sc.items()]
    return man, res


def test_analysis_computations_on_synthetic_records():
    man, res = _synthetic()
    out = hr.analyse_records(man, res, "TEST")
    ra = out["replay_agreement"]
    assert ra["per_query"]["D_both/junction_run_0000/k031"]["gap"] == pytest.approx(0.5)
    assert ra["gate_agreement"]["agree"] == 3 and ra["gate_agreement"]["disagree"] == []
    assert ra["criterion"]["median_abs_gap"] == pytest.approx(0.0) and ra["criterion"]["met"] is True
    num = out["numerical"]
    assert num["N_repeat"] == pytest.approx(0.1) and num["repeats_bit_identical"] is False
    assert num["N_batch"]["C_verify/junction_run_0000/k031"] == pytest.approx(0.25)
    assert num["N_order"]["C_verify/junction_run_0000/k031"] == pytest.approx(-0.1)
    h1 = {p["query_id"]: p for p in out["arms"]["H1_repeated_static"]["per_call"]}
    assert h1["C_verify/junction_run_0000/k031"]["delta"] == pytest.approx(1.0) and h1["C_verify/junction_run_0000/k031"]["flip"] == "accept_to_reject"
    assert h1["D_both/junction_run_0000/k031"]["delta"] == pytest.approx(-2.0) and h1["D_both/junction_run_0000/k031"]["flip"] == "reject_to_accept"
    assert h1["D_both/junction_run_0000/k032"]["flip"] is None
    assert h1["C_verify/junction_run_0000/k031"]["delta_over_episode_ref"] == pytest.approx(0.5)
    assert h1["C_verify/junction_run_0000/k031"]["margin_logged"] == pytest.approx(0.745)
    route = out["arms"]["H1_repeated_static"]["summary"]["junction_run_0000"]
    assert route["n"] == 3 and route["flips_accept_to_reject"] == 1 and route["flips_reject_to_accept"] == 1
    assert route["delta"]["median"] == pytest.approx(0.5)
    assert out["arms"]["H1_repeated_static"]["summary"]["junction_run_0001"]["n"] == 0
    summ = out["arms"]["H1_repeated_static"]["summary"]["D_both/junction_run_0000"]
    assert summ["flips_reject_to_accept"] == 1 and summ["flips_accept_to_reject"] == 0
    assert summ["delta"]["median"] == pytest.approx(-0.75)
    assert all(not p["exceeds_N_repeat"] for p in out["arms"]["H3_own_history_shifted5"]["per_call"])
    pairs = {tuple(p["pair"]): p for p in out["arms"]["H2_posematched_other_variant"]["pairs"]}
    mutual = pairs[("C_verify/junction_run_0000/k031", "D_both/junction_run_0000/k031")]
    assert mutual["mutual"] and mutual["value"] == pytest.approx(0.0)
    single = pairs[("C_verify/junction_run_0000/k031", "D_both/junction_run_0000/k032")]
    assert not single["mutual"] and single["value"] == pytest.approx(0.4)
    assert hr._q([1, 2, 3, 4], .25) == pytest.approx(1.75)


def test_hashes_subcommand_and_expected_runner_digest(complete, tmp_path):
    inside = os.path.join(complete, "h.json")
    p = subprocess.run([sys.executable, RUNNER, "hashes", "--attempt-dir", complete, "--out", inside],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and not os.path.exists(inside)
    out = tmp_path / "h.json"
    p = subprocess.run([sys.executable, RUNNER, "hashes", "--attempt-dir", complete, "--out", str(out)],
                       capture_output=True, text=True, timeout=60)
    rec = _read_json(out)
    assert p.returncode == 0 and rec["files"]["results.jsonl"] == hr.sha_file(os.path.join(complete, "results.jsonl"))
    assert hr.admit(complete, accept_test=True, expected_runner_sha256=hr.sha_file(RUNNER)) == (True, [])
    ok, reasons = hr.admit(complete, accept_test=True, expected_runner_sha256="0" * 64)
    assert not ok and "attempt runner digest differs from the expected frozen digest" in reasons


def test_corrupt_result_line_refused_not_raised(complete):
    a = _copy(complete)
    lines = results(a)
    lines[5] = "{not json"
    _write_text(os.path.join(a, "results.jsonl"), "\n".join(lines) + "\n")
    plan = _read_json(os.path.join(a, "plan.json"))
    plan["mode"] = "PRODUCTION"
    hr.write_json(os.path.join(a, "plan.json"), plan)
    ok, reasons = hr.admit(a)
    assert not ok and "line 5 unreadable" in reasons


def test_evidence_root_required_and_checked(tmp_path):
    a = attempt_dir("noevidence")
    base = [sys.executable, RUNNER, "run", "--manifest", MANIFEST, "--manifest-sha256", MANIFEST_SHA,
            "--attempt-dir", a, "--test-mode", "--backend", f"{SUBS}::Ok"]
    p = subprocess.run(base, capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "--evidence-root" in p.stderr and not os.path.exists(a)
    p = subprocess.run([*base, "--evidence-root", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "lacks the four episode records" in p.stdout and not os.path.exists(a)
