# Linear CPU import audit v5SOURCE-CHECKED DIAGNOSTIC FREEZE, NOT RUN.

The v4 worker exhausted its 60-second watchdog without an audit report. Phase remains UNKNOWN. Static code establishes that every selected-object check rebuilt/resolved the 2757-entry manifest, giving repeated N×M metadata work; this is a performance hypothesis for the timeout, not a measured blocking-phase diagnosis.

V5 builds the authenticated manifest path map once, hashes each encountered source once per audit pass, and retains every object result including all rejections. Fsynced worker/import/audit/object progress is saved before completion. Hash-cache lifetime is this single unchanged process pass; later native-model pre/post checks require separate fresh passes, not reuse of this cache. Source/binary/object authentication is unchanged, including exact VF class methods/export/member identity. No model construction/CUDA API call, environment widening or timeout increase.

Use the hermetic parent interpreter with scripts/run_dependency_import_audit_v5.py --freeze EXACT_COMMIT --stage imports --out /home/favl/navfm-runtime-evidence/dependency-import-audit-v5-01. One child, 60 seconds, CUDA_VISIBLE_DEVICES empty; no initialization stage is admitted by this launcher. Previous freezes/failures remain unchanged and external. All imported-object coverage is limited to the recorded import sequence.
