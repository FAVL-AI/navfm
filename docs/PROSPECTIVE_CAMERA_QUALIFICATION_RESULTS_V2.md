# Prospective known-fixture qualification v2

Branch `agent/research-three-model-plan`; source freeze `3954fb8daf1de1d2a991a7df20a1effe93bdcba1`. The single authorized 120-second qualification **PASS** applies only to the known kinematic camera/label fixture. It is not robot-motion qualification, fresh-data collection, or model evaluation. The [original FAIL](PROSPECTIVE_CAMERA_QUALIFICATION_RESULTS_V1.md) and private seal remain unchanged.

The child exited **0**, was reaped, and did not time out; occupied whole-process wall time was **23.291009 seconds**. Before SDK shutdown, the durable measurement capsule recorded all **19/19 PASS** candidates in the frozen 16+1+1+1 route order. Parent admission verified the capsule source/schema, exact artifact inventory and frame/image identity, and all **27 final ledger artifact hashes** matched. Same-snapshot native ReferenceTime/RGB, held-pose global time, usability, shape and float32-aware pose criteria remained unchanged. Images were 240×320×4; maximum original world-position representation residual was 3.051757815342171e−6 m, handled by the frozen float32 comparison.

Measurement completion and cleanup are distinct. The legacy post-shutdown Python capture snapshot remains `STARTED`, and its terminal write did not occur. SDK cleanup completion is **NOT_INDEPENDENTLY_OBSERVED**. Overall v2 admission uses the verified pre-shutdown measurement capsule plus actual exit 0/no timeout/reaping; it does not infer cleanup completion or retroactively change v1 admission.

External evidence: `/home/favl/navfm-training-evidence/prospective-offline-v2-qualify-01`.

| Artifact | SHA256 |
|---|---|
| ledger.json | `507a7d885532740892d62472e9c297b851a8f8790f96a3fb96fcdab075a69fd0` |
| measurement_complete.json | `b9f20de5105abc58707c46e0a809c51b19d4f64ef4e1425b2cfe67268b8bd48f` |
| capture.json | `51681a9a7d20cd45e3ad20154915ea3f8cf0b2c61d1320fdfc7c8b0714a04c88` |
| process.log | `d6ae856673554d7f534f519eacf6db71513bd58fd4b966fd9b3c268c16b1c1fa` |

Validation: 8 focused preparation controls and Ruff PASS; source/input/opaque seal-chain preflight PASS; capsule validation, final artifact hashes and process admission PASS. The review caught a negative-control masking defect before launch: corrected tests independently exercise verified-capsule abnormal exit, timeout with exit 0 and unreaped child. No second simulator attempt, threshold change, fresh seed regeneration or private seal-content inspection occurred.

All images, labels, raw capsule/logs and private binding remain external. No collection or scoring stage ran. Next decision: separately authorize a versioned fresh-data collection stage that consumes this qualification identity and preserves the existing seal chain; neither old v1 registry nor its FAIL is rewritten. Physical navigation remains blocked by the independently unqualified plant.
