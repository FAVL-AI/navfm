# F-PILOT-1 — REFUTED: "Isaac Sim is not installed on this machine"

**Classification:** false negative from an inadequate search, asserted as a
finding against correct documentation.

**Status: the original finding below is REFUTED.** Isaac Sim 5.1.0.0 *is*
installed and *does* run on this machine. The standing-instructions file was
correct; this record was not.

**Authorship acknowledged.** Introduced by the assistant, asserted with
confidence, and refuted by the supervisor stating the plain fact that Isaac Sim
is installed. The original text is retained verbatim below because deleting a
refuted finding hides the failure that produced it.

---

## What is actually true

| | |
|---|---|
| Isaac Sim | **5.1.0.0**, 25 `isaacsim-*` pip packages |
| Environment | `~/miniforge3/envs/isaac` (conda), Python **3.11.15** |
| Headless bring-up | `SimulationApp({"headless": True})` → **app ready in 68.5 s** |
| `isaacsim.core.api` / `.core.prims` / `.sensors.camera` / `.storage.native` | **all import** after Kit bootstraps |
| Physics | `SimulationContext.initialize_physics()` + 3 steps **OK** |
| GPU | RTX 4080 SUPER, 16 GiB, sm_89; CUDA Toolkit 12.8, Warp 1.8.2 |

This matches the standing-instructions file exactly, including the two-
environment rule: `~/.venv-train` and the Isaac Sim 5.1 Python environment are
separate and never merged, so `import isaacsim` failing in `~/.venv-train` is
the documented, correct behaviour — not evidence of absence.

## Why the search returned a false negative

Three specific inadequacies, each of which alone would have been enough:

1. **The conda root was enumerated by guessing names.** The probe listed
   `~/miniconda3/envs`, `~/anaconda3/envs` and `~/mambaforge/envs`. The actual
   root is `~/miniforge3/envs`. A name not on the guess-list reads as "no conda
   environments exist".
2. **The filesystem search looked for the wrong artefacts.** It searched for
   `python.sh`, `isaac-sim.sh` and `isaac-sim.selector.sh` — the launcher-bundle
   layout. A pip-installed Isaac Sim has none of them; it has
   `site-packages/isaacsim/`. The search could not have found a pip install
   however deep it went.
3. **`import isaacsim` was run in the wrong interpreter.** It was run in
   `~/.venv-train`, where failure is *required* by the documented two-environment
   separation. That result was read as a fact about the machine rather than a
   fact about one virtualenv.

`~/.local/share/ov/pkg/` containing only `hub-2.0.0` was then read as
corroboration — "the launcher is present, the runtime was never installed". It
is equally consistent with a pip install that never used the launcher, which is
what happened.

## The failure this actually records

Not a missing runtime. **A negative result from a search is only as strong as
the search, and this one was treated as strong enough to contradict
documentation.**

The standing-instructions file states these environment facts and says "do not
'fix' them". The correct response to an apparent contradiction was to suspect
the probe, because the probe was written in five minutes and the documentation
was written by someone with direct knowledge of the machine. Instead a failure
record was filed asserting the documentation false, committed, and pushed.

This is the mirror image of F-M2-1 and F-M2-4, which are about checks that
cannot fail. This is a check that **failed for the wrong reason and was
believed**. Both produce a confident wrong answer; only the direction differs.

**Generalisation.** Before reporting that something documented is absent:
enumerate roots by discovery (`find -name pyvenv.cfg`, `find -name "isaacsim*"`)
rather than by a list of guessed names; search for the artefact in every layout
it can take, not one; and run an import probe in the interpreter that is
supposed to have it. State the search's coverage alongside its result, so a
reader can see what it could not have found. "Not found" is not "not present",
and the difference matters most when the claim contradicts someone who knows.

## Cost

One blocked session, one false record committed and pushed, and a request to the
supervisor to resolve a question that was already answered correctly in the
repository. The harness work done during the block was independently useful and
stands (`gates/pilot/`), but it was undertaken on a false premise.

---

# Original finding, as filed — REFUTED, retained verbatim

> # F-PILOT-1 — Isaac Sim is not installed on this machine; the pilot is Blocked at bring-up
>
> **Classification:** documented environment does not match actual environment. A
> planning assumption asserted as an environmental fact, relied on across several
> sessions, and false.
>
> **Status:** BLOCKING. No trajectory was collected. No substitute data was
> produced.
>
> ## What the standing-instructions file asserts
>
> Under "Environment on this machine (facts, do not 'fix' them)":
>
> > **Isaac Sim 5.1.0 is installed. Do NOT upgrade to 6.x.** 5.1 is the stable
> > Isaac Lab pairing (Python 3.11).
>
> The parenthetical instructs that these are facts not to be "fixed", so they were
> carried as given. They were not verified until collection was actually attempted.
>
> ## What is on the machine
>
> | Probe | Result |
> |---|---|
> | `find / -maxdepth 6 -name python.sh -o -name isaac-sim.sh -o -name isaac-sim.selector.sh` | no results |
> | `python -c "import isaacsim"` | `ModuleNotFoundError: No module named 'isaacsim'` |
> | `python -c "import isaaclab"` | `ModuleNotFoundError: No module named 'isaaclab'` |
> | `ls ~/.local/share/ov/pkg/` | `hub-2.0.0` only |
> | `/isaac-sim`, `~/isaac-sim`, `~/isaacsim`, `/opt/nvidia/isaac*` | none exist |
> | `docker images \| grep isaac` | none |
> | `lsblk` | single NVMe, no external mount that could host it |
> | `/opt/ros/` | `humble` — present, as documented |
> | `nvidia-smi` | RTX 4080 SUPER, driver 580.159.03, 16376 MiB — present, as documented |
>
> `hub-2.0.0` is the Omniverse Launcher hub — the component that *downloads*
> packages. Its presence is consistent with an intent to install Isaac Sim and
> with the install never having completed. Nothing else in `ov/pkg` exists.
>
> The GPU, driver and ROS 2 Humble claims in the standing-instructions file are
> correct. The Isaac Sim claim is not.
>
> ## Consequence
>
> [...] Every plan that treated bring-up as "expect API friction on first 5.1 run"
> assumed a runtime that is not present. The friction is not API-level; there is
> no runtime to import.
>
> ## The rule this is an instance of
>
> The gate discipline already says: *gate scripts never infer execution state —
> preflight, refuse, and name the missing requirement* (F-M1-1). That rule was
> written for scripts. This is the same failure at the planning layer [...]

The retained text's closing rule is correct in the abstract and was applied to
the wrong subject. The precondition was not unverified — it was verified badly,
and the bad verification was trusted over the documentation it contradicted.
