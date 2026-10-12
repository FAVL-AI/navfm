# Synthetic stopping component qualification v1 result

**PASS_SYNTHETIC_COMPONENTS_ONLY. Navigation, VPR/encoder integration,
controller STOP and physical qualification remain BLOCKED.**

The single authorized attempt ran from clean reviewed freeze
`ea1b3dc75463ff8bfd2a71ae23270238494424f0`, after source publication, with no
retry. The parent exited zero, verified the worker/result source identities,
observed exit zero, no timeout and reaping. Worker checks took **0.317940 s**;
parent supervision took **0.416163 s**. There were **64 native match calls**,
zero GPU calls and **9,647 external artifact bytes**, within the declared caps.
The attempt-start record remains STARTED as an immutable start event; distinct
worker and parent terminal records both report PASS.

Exact same-dtype initialized beliefs/lambda, updated posteriors, MAP/confidence
and independent native BASS localization/path/subgoal state agree for the four
comparator/dtype cases (PlaceNav and released ROS ULVN, float32 and float64).
Twenty-four frame observations and four completed case records are preserved
among 80 durable partial events. The probe also checks fresh reset/state
isolation, unsupported and descriptor-tied goals, ULVN weighted-vs-binary graph
behavior, the native arrival conjunction/sticky state, and None-subgoal
publication suppression with a seeded-latch fault control.

Native numerical limits remain visible: PlaceNav's equal-quantile case yields
an invalid native belief and is classified ABSTAIN, without a new mathematical
fallback. ULVN's released equal-quantile lambda fallback remains one; deliberately
underflowed likelihood is ABSTAIN, without importing the core library's different
uniform fallback. These controls qualify documented refusal/finite-domain
behavior, not recovery performance or broad numerical robustness.

The [frozen protocol](STOP_INTERFACE_QUALIFICATION_V1.md) and
[independent source review](STOPPING_COMPARATOR_FIDELITY_REVIEW_V1.md) distinguish
native component/arrival evidence from complete systems. The recorded
STOP proposal is a downstream adaptation with controller integration BLOCKED.
The released ULVN local planner does not consume its sticky arrival flag;
native actuator STOP parity remains unestablished. Native VPR encoders,
RGB/reference acquisition, graph construction, checkpoint inference and the
common four-Hz image pipeline were not run or qualified.

External evidence directory:
`/home/favl/navfm-runtime-evidence/stop-interface-v1-synthetic-01`.
Config SHA-256: `599ec7dd33403a28e7cff537ca37008a45d5e552adfc0e0ce0519e618019cd8c`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| attempt.json | 189 | `5e3e5192d8d35afa3fab3a1d5e76c336722fb6ceb34fa09c69a1ea15f053b9f8` |
| partial.jsonl | 8,820 | `32d6e7d4983faa459a42b8f59930d39c38d8193105c59582b22ba1cb7af33d5c` |
| result.json | 290 | `446beca05952353b014c33540cb7bff98914790250de818b4aff1b09de5fb4a5` |
| worker_status.json | 79 | `ffd2015ba8d84363763fe325b2943f5db9ee4e2d2bee86fea8caeb18eac7b76f` |
| parent_status.json | 269 | `f3b8a927fa625aa121c88d29cc32c208892af385f9854361c03271d46533d931` |
| worker.log | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

No images, weights, geometry, raw trajectories or logs are committed. No neural checkpoint
inference, fitting, simulator, navigation study, test access or robot actuation
occurred. The prior 29 prerequisite failures remain unresolved; hermetic guard
checks and this native-component result do not replace missing resources.
CAD/STEP/converter access and the sphere-based plant remain BLOCKED. The closed
pilot, DEV feasibility protocol, illumination pause, held-out seal and larger
benchmark/resource authorization are unchanged.

Next decision: separately qualify admitted RGB descriptors/reference graphs and
actual STOP integration, or resolve authentic CAD/plant/controller/contact
prerequisites. This result itself authorizes neither.
