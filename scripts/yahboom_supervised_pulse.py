"""Bounded manual qualification pulse; dry-run default, never used for navigation."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topic", required=True, help="operator verified hardware command topic")
    p.add_argument("--v", type=float, default=0)
    p.add_argument("--w", type=float, default=0)
    p.add_argument("--seconds", type=float, default=2)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--execute-supervised", action="store_true")
    a = p.parse_args()
    if not abs(a.v) <= 0.05 or not abs(a.w) <= 0.2 or not 0 < a.seconds <= 2:
        p.error("pulse limits .05m/s,.2rad/s,2s")
    if a.out.exists():
        p.error("new output required")
    a.out.mkdir(parents=True)
    r = {
        "status": "DRY_RUN",
        "command": [a.v, 0, a.w],
        "seconds": a.seconds,
        "topic": a.topic,
        "measured_displacement_m": None,
        "measured_yaw_rad": None,
        "measured_stop_distance_m": None,
        "measured_residual_motion": None,
        "measurements_required": "external tracking or tape/video; sign, achieved velocity, stop travel, residual, acquisition/command clock correspondence",
        "submitted": [],
    }
    if a.execute_supervised:
        import rclpy
        from geometry_msgs.msg import Twist

        rclpy.init()
        node = rclpy.create_node("yahboom_qualification")
        pub = node.create_publisher(Twist, a.topic, 1)
        try:
            deadline = time.monotonic() + a.seconds
            while time.monotonic() < deadline:
                m = Twist()
                m.linear.x = a.v
                m.angular.z = a.w
                pub.publish(m)
                r["submitted"].append(time.time())
                rclpy.spin_once(node, timeout_sec=0.05)
            r["status"] = "SUBMITTED_MEASUREMENTS_PENDING"
        finally:
            for _ in range(10):
                pub.publish(Twist())
                rclpy.spin_once(node, timeout_sec=0.05)
            node.destroy_node()
            rclpy.shutdown()
    (a.out / "pulse.json").write_text(json.dumps(r, indent=2) + "\n")
    print(r["status"])


if __name__ == "__main__":
    main()
