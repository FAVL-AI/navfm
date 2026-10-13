# Exact native ViNT manifest completion v2

Status: REVIEWED FREEZE / CPU import closure PASS / fresh component qualification NOT RUN. Branch `agent/research-three-model-plan`, baseline `3bd63381a03ce02e83dec4bb18fdbbded754c8a5`. Original failures, checkpoints, model/input/validation code and all authentication/generated-module acceptance rules are immutable.

The sole compatibility addition is the persistent module `vint_train.models.vint.vint`, resolved to existing pinned upstream `train/vint_train/models/vint/vint.py`, SHA `1af3afb275f6f52d643df792cf39d8bb77e0fe00f06d7ceb9c152a408554ad37`. The recipe requires agreement with the already frozen upstream record and actual file bytes. The versioned manifest retains every prior file/loaded/generated entry unchanged and adds this file plus the two new recipe/launcher control sources. No directory, namespace, temporary-module exemption or checkpoint change is introduced.

Before CUDA, the exact worker interpreter with CUDA hidden imported native ViNT/image/loader/control paths, constructed no model and read no weights. One-pass inventory covered 2,214 loaded file records; zero unaccepted origins/hashes were found, then the original verifier passed. Only aliases of the same transient stdin harness object (`__main__`, `__mp_main__`) were excluded, not a production verifier rule. The earlier recipe invocation failed before creating a manifest because its output parent did not exist; the recipe now creates its external parent before atomic persistence. No model attempt was consumed.

CPU evidence: `/home/favl/navfm-training-evidence/vint-interface-v2-cpu-import-01`; manifest: `/home/favl/navfm-training-evidence/vint-interface-v2/native-source-closure.json`. Both are hash-bound inputs. One focused original-verifier control checks exact-entry PASS and rejects changed bytes, identical bytes at a foreign origin, and an unexpected additional file; Ruff passes. Population retains all prior nodes and adds that one pure control.

After the bounded manifest review and published exact freeze: **one fresh four-role/two-case synthetic qualification, 150 seconds whole process, 145 child plus five cleanup**. Existing diagnostic worker, first-rejection retention and actual parent code/timeout/reap reporting are reused. Native load/reload, finite XY/heading, state/RNG and pre/post/final provenance gates remain unchanged; a new failure is preserved without retry. No scoring, training, data collection or simulator is authorized by this protocol.

```sh
PYTHONPATH=src NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/upstream /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/run_vint_interface_qualification_v2.py --freeze FULL_REVIEWED_COMMIT --out /home/favl/navfm-training-evidence/vint-interface-v2-qualification-01
```

Six intended files: exact manifest recipe, versioned launcher/config, this protocol, focused tests and population. Generated manifest/evidence/weights remain external. Complete qualification must be established before any separately frozen/authorized ViNT pair scoring.
