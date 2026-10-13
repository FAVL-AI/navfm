"""One strict-load/native-forward compatibility probe; no optimizer or simulator."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads(a.config.read_text())
    role = cfg["models"][a.role]
    os.environ["NAVFM_UPSTREAM"] = cfg["upstream"]
    report = {"status": "FAIL", "role": a.role, "training": False, "simulator": False}
    start = time.monotonic()
    try:
        import torch
        from PIL import Image

        from navfm import upstream
        from navfm.models.loader import extract_state_dict, load_checkpoint

        if not torch.cuda.is_available():
            raise ValueError("CUDA required; no CPU fallback")
        torch.manual_seed(4080)
        torch.cuda.manual_seed_all(4080)
        upstream.ensure_upstream()
        mc = upstream.model_config(role["model"])
        if role["model"] == "nomad":
            spec = importlib.util.spec_from_file_location(
                "qualified_nomad_builder", ROOT / "scripts/verify_r6_strict_load.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            model = mod._build_nomad(mc)
        else:
            model = upstream.build_model(role["model"], mc)
        model.load_state_dict(
            extract_state_dict(
                load_checkpoint(
                    Path(role["checkpoint"]), trust_checkpoint=True, expected_sha256=role["sha256"]
                )
            ),
            strict=True,
        )
        model.to("cuda").eval()
        from vint_train.data.data_utils import resize_and_aspect_crop

        image = Image.open(cfg["goal_image"]).convert("RGB")
        x = resize_and_aspect_crop(image, tuple(mc["image_size"]))
        x = (x - x.new_tensor([0.485, 0.456, 0.406])[:, None, None]) / x.new_tensor(
            [0.229, 0.224, 0.225]
        )[:, None, None]
        goal = x.unsqueeze(0).cuda()
        obs = torch.cat([x] * (mc["context_size"] + 1)).unsqueeze(0).cuda()
        with torch.inference_mode():
            if role["model"] == "nomad":
                from diffusers.schedulers.scheduling_ddpm import DDPMScheduler

                condition = model(
                    "vision_encoder",
                    obs_img=obs,
                    goal_img=goal,
                    input_goal_mask=torch.zeros(1, dtype=torch.long, device="cuda"),
                )
                distance = model("dist_pred_net", obsgoal_cond=condition)
                actions = torch.randn((1, mc["len_traj_pred"], 2), device="cuda")
                scheduler = DDPMScheduler(
                    num_train_timesteps=10,
                    beta_schedule="squaredcos_cap_v2",
                    clip_sample=True,
                    prediction_type="epsilon",
                )
                scheduler.set_timesteps(10)
                for step in scheduler.timesteps:
                    noise = model(
                        "noise_pred_net", sample=actions, timestep=step, global_cond=condition
                    )
                    actions = scheduler.step(noise, step, actions).prev_sample
            else:
                distance, actions = model(obs, goal)
        torch.cuda.synchronize()
        if not torch.isfinite(distance).all() or not torch.isfinite(actions).all():
            raise ValueError("nonfinite outputs")
        if list(actions.shape) != [1, mc["len_traj_pred"], 4 if mc["learn_angle"] else 2]:
            raise ValueError("native action geometry mismatch")

        def digest(t):
            return hashlib.sha256(t.detach().cpu().numpy().tobytes()).hexdigest()

        report.update(
            status="PASS",
            config=mc,
            strict_load=True,
            obs_shape=list(obs.shape),
            goal_shape=list(goal.shape),
            obs_sha256=digest(obs),
            goal_sha256=digest(goal),
            distance=distance.detach().cpu().tolist(),
            actions=actions.detach().cpu().tolist(),
            checkpoint_sha256=role["sha256"],
            torch=torch.__version__,
            cuda=torch.version.cuda,
            device=torch.cuda.get_device_name(0),
            device_type="cuda",
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
            cudnn_benchmark=torch.backends.cudnn.benchmark,
            cudnn_deterministic=torch.backends.cudnn.deterministic,
            diffusion_iterations=10 if role["model"] == "nomad" else 0,
            samples=1,
        )
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        report["wall_s"] = time.monotonic() - start
        a.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
