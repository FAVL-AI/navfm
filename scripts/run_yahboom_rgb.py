"""Supervised ROS RGB adapter. Offline software checks use check_yahboom_adapter.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--goal", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--camera-topic", required=True)
    p.add_argument("--command-topic", required=True)
    p.add_argument(
        "--execute-supervised",
        action="store_true",
        help="operator starts only after physical qualification and emergency stop check",
    )
    a = p.parse_args()
    if not a.execute_supervised:
        p.error(
            "no hardware publication without explicit supervised execution; use saved-RGB software check"
        )
    c = json.loads(a.calibration.read_text())
    required = [
        "fx",
        "fy",
        "cx",
        "cy",
        "distortion",
        "mount_xyz",
        "mount_rpy",
        "width",
        "height",
        "camera_timestamp_clock",
        "command_mapping",
        "watchdog_verified",
        "controller_qualified",
    ]
    if (
        any(c.get(k) is None for k in required)
        or not c["watchdog_verified"]
        or not c["controller_qualified"]
    ):
        p.error("measured camera/controller qualification incomplete")
    import rclpy
    from geometry_msgs.msg import Twist
    from PIL import Image
    from sensor_msgs.msg import Image as RGBImage

    from navfm.collection.rgb_baseline import RGBBaseline
    from navfm.deployment.yahboom import YahboomAdapter

    policy = RGBBaseline(
        a.checkpoint, action_scale_m=0.049994826316833496, stop_enabled=True, max_v=0.1
    )
    goal = np.asarray(Image.open(a.goal).convert("RGB"))
    rclpy.init()
    node = rclpy.create_node("yahboom_rgb_navigation")
    pub = node.create_publisher(Twist, a.command_topic, 1)

    def sink(command):
        m = Twist()
        m.linear.x = float(command[0])
        m.linear.y = float(command[1])
        m.angular.z = float(command[2])
        pub.publish(m)

    adapter = YahboomAdapter(policy, goal, sink)

    def callback(msg):
        try:
            if (
                msg.width != c["width"]
                or msg.height != c["height"]
                or msg.encoding not in ("rgb8", "bgr8")
            ):
                raise ValueError("camera mode mismatch")
            rgb = (
                np.frombuffer(msg.data, np.uint8)
                .reshape(msg.height, msg.step)[:, : msg.width * 3]
                .reshape(msg.height, msg.width, 3)
            )
            if msg.encoding == "bgr8":
                rgb = rgb[:, :, ::-1].copy()
            ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            now = node.get_clock().now().nanoseconds * 1e-9
            adapter.observe(rgb, ts, now)
        except Exception as e:
            adapter.stop()
            node.get_logger().error(str(e))

    def watchdog():
        now = node.get_clock().now().nanoseconds * 1e-9
        if adapter.last_timestamp is None or now - adapter.last_timestamp > 0.2:
            adapter.stop()

    node.create_subscription(RGBImage, a.camera_topic, callback, 1)
    node.create_timer(0.05, watchdog)
    try:
        rclpy.spin(node)
    finally:
        adapter.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
