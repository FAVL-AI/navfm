# Native NoMaD EMA integration v3

This version repairs only the removed integration lookup between installed Diffusers 0.29.2 and Transformers 4.57.6. The prior NoMaD partial failure and GNM six-update PASS remain immutable. Status: reviewed source freeze; GPU attempt NOT RUN.

The adapter authenticates the installed source paths and hashes and the loaded native step/API code. It replaces exactly two `transformers.deepspeed` lookups with the documented `transformers.integrations.deepspeed` module in a copied function namespace. It preserves the native step body, decorator, decay, trainable subtraction, frozen-parameter copy and counter semantics. It neither modifies installed packages nor invents a compatibility alias.

Primary references: [Diffusers 0.29.2 native EMA](https://github.com/huggingface/diffusers/blob/v0.29.2/src/diffusers/training_utils.py), [Transformers 4.57.6 integration API](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/integrations/deepspeed.py).

Five focused controls pass: native trainable/frozen shadows and counter progression; serialized next-update equality; exact AST reversal proving only two lookups change; altered source hash rejection; altered loaded API/native step rejection. Counter 1 copies values; counter 2 uses nonzero warmup decay. The complete CPU preflight also imports the declared native closure, constructs NoMaD train/development batches, verifies origins and runs that actual EMA control with CUDA hidden. The first invocation lacked the explicit project import path and failed before native imports; that report is preserved. Corrected invocation 02 PASS. Lint was run through the installed standalone executable after the worker environment correctly reported no Ruff module.

Configuration: `configs/train/native_adaptation_smoke_v3.json`. External proof and dependency snapshot: `/home/favl/navfm-training-evidence/native-ema-closure-v3/`. The configuration digest binds all consumed input paths/hashes, excluding only the CPU proof's cyclic self-hash. The original interpreter and all packages remain unchanged. No GNM rerun is scheduled.

After reviewed committed freeze, execute exactly one fresh-release NoMaD smoke, six updates under the unchanged 150-second watchdog:

```sh
PYTHONPATH=src NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/upstream /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/run_native_adaptation_smoke_v3.py --freeze FULL_COMMIT --model nomad --out /home/favl/navfm-training-evidence/native-adaptation-smoke-v3-01
```

Each update journals finite backward, optimizer application, scheduler application and EMA application separately. PASS requires six complete joint transactions, counter 6, finite shadows/model/gradients, strict released load, strict resume and EMA deployment reload, and development state/RNG isolation. An exception preserves incomplete transaction evidence. Start from released weights, never the prior partial state. No unchanged retry or long training follows this smoke; plumbing success does not establish learning benefit or navigation quality. All checkpoints, batch evidence and logs remain external.
