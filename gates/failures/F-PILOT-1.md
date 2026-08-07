# F-PILOT-1 — Isaac Sim is not installed on this machine; the pilot is Blocked at bring-up

**Classification:** documented environment does not match actual environment. A
planning assumption asserted as an environmental fact, relied on across several
sessions, and false.

**Status:** BLOCKING. No trajectory was collected. No substitute data was
produced.

## What the standing-instructions file asserts

Under "Environment on this machine (facts, do not 'fix' them)":

> **Isaac Sim 5.1.0 is installed. Do NOT upgrade to 6.x.** 5.1 is the stable
> Isaac Lab pairing (Python 3.11).

The parenthetical instructs that these are facts not to be "fixed", so they were
carried as given. They were not verified until collection was actually attempted.

## What is on the machine

| Probe | Result |
|---|---|
| `find / -maxdepth 6 -name python.sh -o -name isaac-sim.sh -o -name isaac-sim.selector.sh` | no results |
| `python -c "import isaacsim"` | `ModuleNotFoundError: No module named 'isaacsim'` |
| `python -c "import isaaclab"` | `ModuleNotFoundError: No module named 'isaaclab'` |
| `ls ~/.local/share/ov/pkg/` | `hub-2.0.0` only |
| `/isaac-sim`, `~/isaac-sim`, `~/isaacsim`, `/opt/nvidia/isaac*` | none exist |
| `docker images \| grep isaac` | none |
| `lsblk` | single NVMe, no external mount that could host it |
| `/opt/ros/` | `humble` — present, as documented |
| `nvidia-smi` | RTX 4080 SUPER, driver 580.159.03, 16376 MiB — present, as documented |

`hub-2.0.0` is the Omniverse Launcher hub — the component that *downloads*
packages. Its presence is consistent with an intent to install Isaac Sim and
with the install never having completed. Nothing else in `ov/pkg` exists.

The GPU, driver and ROS 2 Humble claims in the standing-instructions file are
correct. The Isaac Sim claim is not.

## Consequence

`src/navfm/isaac/{app,robot,randomize,collect}.py` were already marked
"implemented but NEVER EXECUTED". The reason recorded for that was "no Isaac Sim
in the build environment", which implied the build environment differed from
this machine. It does not differ in this respect: Isaac Sim is absent here too.
Every plan that treated bring-up as "expect API friction on first 5.1 run"
assumed a runtime that is not present. The friction is not API-level; there is
no runtime to import.

## What was NOT done, and why

* **Isaac Sim was not installed.** It is a multi-gigabyte download requiring
  account authentication, and the standing instructions pin a specific version
  with an explicit prohibition on 6.x. Selecting and installing a version is a
  decision with a wrong answer, and it is the supervisor's to make, not a step
  to take silently in order to unblock a task.
* **No substitute data was produced.** Writing synthetic arrays into the Option 1
  layout would produce two directories that pass every compatibility check and
  demonstrate nothing about collection, because the collector would never have
  run. The pilot's stated success condition is that *collected* data are
  accepted by the unchanged ViNT data path. Data that was not collected cannot
  satisfy it, however green the report looks.
* **`scripts/smoke_isaac.py` and `src/navfm/isaac/urdf_import.py` were not
  created.** The instruction was to create them only if bring-up demonstrates
  they are required. Bring-up demonstrated something upstream of them.

## The rule this is an instance of

The gate discipline already says: *gate scripts never infer execution state —
preflight, refuse, and name the missing requirement* (F-M1-1). That rule was
written for scripts. This is the same failure at the planning layer: an
environmental precondition was documented, restated across sessions, and never
preflighted, so it was discovered at the point of use rather than the point of
planning.

**Generalisation:** a documented environment fact is a claim, not a
verification. Preconditions that gate a phase should be probed when the phase is
planned, not when it executes. The cost here was one blocked session; the same
error against a booked hardware slot or a supervisor meeting costs the slot.
