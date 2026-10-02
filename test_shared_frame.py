"""
test_shared_frame.py -- checks the connection to the frame-sharing build of
NTRViewer-HR, without pressing any buttons.

    py test_shared_frame.py              (uses the rotation in config.json)
    py test_shared_frame.py --rotation 3 (try another rotation: 0, 1, 2 or 3)

It reports the frame rate and connection quality for a few seconds, then
saves shared_frame_test.png. Open that picture: the game should be the
right way up, with black bars at the left and right. If it's sideways or
upside down, try other --rotation values, then put the one that works in
config.json as  "shared_rotation": N
"""
import argparse
import json
import time

import cv2

import shared_frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotation", type=int, default=None)
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args()
    rotation = args.rotation
    if rotation is None:
        try:
            with open("config.json") as f:
                rotation = json.load(f).get("shared_rotation", 1)
        except (OSError, ValueError):
            rotation = 1
    cap = shared_frame.SharedFrameCapture(rotation=rotation)
    print("Waiting for the frame-sharing NTR Viewer...")
    if not shared_frame.wait_until_available(cap, timeout=15.0):
        print("Nothing yet. Check that you started the frame-sharing build of "
              "NTRViewer-HR (not the original) and that it shows the game.")
        return
    print(f"Connected. Watching for {args.seconds:.0f} s (move something in the "
          f"game to see frames arrive -- a still screen sends none):")
    start_index = cap.frame_index()
    end = time.time() + args.seconds
    while time.time() < end:
        time.sleep(1.0)
        q = cap.quality()
        print(f"  frames so far: {cap.frame_index() - start_index:5d} | connection "
              f"quality: {'unknown' if q is None else f'{q:.1f}%'}")
    frame = cap.frame()
    cv2.imwrite("shared_frame_test.png", frame)
    print(f"Saved shared_frame_test.png ({frame.shape[1]}x{frame.shape[0]}, "
          f"rotation {rotation}). Open it: the game should be upright with "
          f"black bars left and right.")


if __name__ == "__main__":
    main()
