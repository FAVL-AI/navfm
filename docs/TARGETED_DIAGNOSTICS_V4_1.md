# Diagnostic preflight amendment v4.1

Freeze8b18152 failed before worker/output creation: KeyError upstream_files in the shared frozen helper. Exact failure remains external at /home/favl/navfm-runtime-evidence/diagnostic-v4-preflight-failure-01/failure.json. No import or initialization attempt was consumed.

V4.1 supplies the unchanged pinned upstream and upstream_files from the reviewed v3 configuration to the shared source guard. All v4 inputs, worker bytes, environment, process counts, budgets and no-active-command rules remain unchanged. A schema control derives every required configuration key from the actual frozen helper and verifies this amendment. Clean committed source guard must pass before either worker. No relaxed integrity check or retry of a worker is introduced.

Use scripts/run_targeted_diagnostics_v4_1.py with the exact amendment commit, the same two stages and external output paths declared in TARGETED_DIAGNOSTICS_V4.md. Runtime evidence stays external; no models or CUDA API calls in the CPU import diagnostic.
