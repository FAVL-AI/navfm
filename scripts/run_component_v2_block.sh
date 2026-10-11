#!/bin/bash
# Launch component_comparison_v2 amendment-2 collections, writing a launch ledger.
#   run_component_v2_block.sh block AMENDMENT_COMMIT LEDGER
#       every route of every replaced cell, in the record's (frozen) order, tag = record "tag"
#   run_component_v2_block.sh stage3 AMENDMENT_COMMIT LEDGER STAGE2_COMMIT STAGE2_PATH
#       every route of every stage-3 cell the committed stage-2 gate record admits (the
#       analysis's required_stage3 rule), in config order, tag = record "stage3_tag"
#   run_component_v2_block.sh rerun AMENDMENT_COMMIT LEDGER TRIAL:VARIANT ROUTE [ROUTE ...]
#       the one permitted rerun of routes whose first attempt is not PASS, for a replaced
#       cell (tag "rerun_tag") or a stage-3 cell (tag "stage3_rerun_tag")
# Refuses a dirty worktree, a HEAD that does not descend from AMENDMENT_COMMIT, a record
# that differs from the one committed there, and an existing output. All collector
# arguments come from the frozen config, exactly as for stage 2.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
E=/home/favl/navfm-runtime-evidence
CFG=configs/eval/component_comparison_v2.json
REC=configs/eval/component_comparison_v2_amendment_2.json
ROBOT=/home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd
MODE=$1; AMC=$2; LEDGER=$3; shift 3
cd "$REPO"
die() { echo "refused: $*" >&2; exit 2; }
[ -z "$(git status --porcelain)" ] || die "worktree is not clean"
git merge-base --is-ancestor "$AMC" HEAD || die "HEAD does not descend from $AMC"
git diff --quiet "$AMC" HEAD -- "$REC" || die "amendment record differs from $AMC"
case $MODE in
    block)
        TAG=$(.venv/bin/python -c "import json;print(json.load(open('$REC'))['tag'])")
        CELLS=$(.venv/bin/python -c "import json;[print(t+':'+v) for t,v in json.load(open('$REC'))['replaced_cells']]")
        ROUTES="" ;;
    stage3)
        TAG=$(.venv/bin/python -c "import json;print(json.load(open('$REC'))['stage3_tag'])")
        CELLS=$(.venv/bin/python - "$1" "$2" "$CFG" <<'PY'
import json, subprocess, sys
sys.path.insert(0, "scripts")
import analyse_component_comparison_v2 as v2
s2 = json.loads(subprocess.run(["git", "show", f"{sys.argv[1]}:{sys.argv[2]}"],
                               capture_output=True, check=True).stdout)
passed = {k for k, g in s2["gates"].items() if isinstance(g, dict) and g.get("status") == "PASS"}
cfg = json.load(open(sys.argv[3]))
req = v2.required_stage3(passed) if passed else set()
for tn, t in cfg["trials"].items():
    if t["stage"] == 3:
        for v in t["variants"]:
            if v in req:
                print(f"{tn}:{v}")
PY
) || die "stage-2 gate record unreadable"
        [ -n "$CELLS" ] || die "no component passed stage 2; stage 3 does not run"
        ROUTES="" ;;
    rerun)
        CELLS=$1; shift; ROUTES="$*"
        [ -n "$ROUTES" ] || die "rerun needs routes"
        read -r TAG FIRST < <(.venv/bin/python - "$REC" "$CFG" "$CELLS" <<'PY'
import json, sys
rec, cfg = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
trial, v = sys.argv[3].split(":")
if [trial, v] in rec["replaced_cells"]:
    print(rec["rerun_tag"], rec["tag"])
elif trial in cfg["trials"] and cfg["trials"][trial]["stage"] == 3:
    print(rec["stage3_rerun_tag"], rec["stage3_tag"])
PY
)
        [ -n "${TAG:-}" ] || die "$CELLS is neither a replaced cell nor a stage-3 cell"
        .venv/bin/python - "$E/v2-${CELLS%%:*}-${CELLS##*:}-$FIRST/collection.json" $ROUTES <<'PY' || die "a route's first attempt is PASS or missing"
import json, sys
seen = {e["id"]: e["status"] for e in json.load(open(sys.argv[1]))["episodes"]}
sys.exit(any(seen.get(r, "CRASHED") == "PASS" for r in sys.argv[2:]))
PY
        ;;
    *) die "mode must be block, stage3 or rerun" ;;
esac
export OMNICLIENT_HUB_MODE=disabled NAVFM_UPSTREAM=$E/option1-admitted-20261007-02/upstream
ROBOT_SHA=$(sha256sum "$ROBOT" | cut -c1-64)
for tv in $CELLS; do
    TRIAL=${tv%%:*}; V=${tv##*:}; OUT=$E/v2-$TRIAL-$V-$TAG
    [ -e "$OUT" ] && die "$OUT exists"
    ARGS=$(.venv/bin/python - "$CFG" "$TRIAL" $ROUTES <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1])); t = cfg["trials"][sys.argv[2]]
routes = sys.argv[3:] or t["routes"]
if not set(routes) <= set(t["routes"]):
    sys.exit("route not in trial")
a = [f"--route-id {r}" for r in t["routes"] if r in routes]  # frozen route order
a.append(f"--topomap-root {cfg['conditions'][t['condition']]['root']}")
a.append(f"--max-steps {t.get('budget_frames', cfg['runtime']['budget_frames'])}")
if t.get("resume_from"):
    a.append(f"--resume-from {t['resume_from']} --resume-decision {t['resume_decision']}")
if t.get("start_lost"):
    a.append("--start-lost")
p = t.get("perturbation")
if p:
    a.append(f"--start-arc-fraction {p[0]} --start-lateral-m {p[1]} --start-yaw-deg {p[2]}")
print(" ".join(a))
PY
) || die "bad routes for $TRIAL"
    .venv/bin/python -c 'import json,sys; print(json.dumps(dict(zip(["collection","head","worktree_status","launch_utc","robot_usd_sha256"], sys.argv[1:]))))' \
        "$(basename "$OUT")" "$(git rev-parse HEAD)" "$(git status --porcelain | tr '\n' ';')" \
        "$(date -u +%FT%TZ)" "$ROBOT_SHA" >> "$LEDGER"
    timeout 5400 /home/favl/miniforge3/envs/isaac/bin/python scripts/collect_option1.py --out "$OUT" \
        --policy-period-frames 6 $ARGS \
        --robot "$ROBOT" \
        --actuation wheel \
        --checkpoint /home/favl/navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth \
        --checkpoint-sha256 c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c \
        --qualification /home/favl/navfm-runtime-evidence/articulated-control-20261009-10/qualification.json \
        --yaw-feedback \
        --goal-root /home/favl/navfm-runtime-evidence/arrival-goal-traversal-final-frame-20261009-01 \
        --comparison-config "$CFG" --variant "$V" --trial "$TRIAL" > "$OUT.log" 2>&1
    rc=$?
    FR=$(sha256sum "$OUT/frozen_routes.json" 2>/dev/null | cut -c1-64)
    printf '{"collection": "%s", "exit": %d, "frozen_routes_sha256": "%s", "robot_usd_sha256_after": "%s"}\n' \
        "$(basename "$OUT")" "$rc" "$FR" "$(sha256sum "$ROBOT" | cut -c1-64)" >> "$LEDGER"
    echo "$TRIAL $V EXIT $rc"
done
echo BLOCK DONE
