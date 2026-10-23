"""
Checks the path the bot actually uses: NTR-VC's shared frames
(the 3DS top screen, Game Boy picture in the middle, scaled x4) going
through frame_recorder.RecordingCapture into shiny_flash -- with simulated
battle starts (see sim_battle.py), no 3DS, no ROM, no Pokemon graphics.

    py -m pytest tests            (or: py tests/test_recording.py)
"""

import os
import sys
import threading
import time as real_time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import frame_recorder                # noqa: E402
import gb_screen                     # noqa: E402
import sim_battle                    # noqa: E402

FPS = 60.0


def top_screen(native, gb_scale):
    """What shared_frame.SharedFrameCapture.frame() returns: the 400x240
    top screen (Game Boy picture centred on black), scaled x4."""
    gb = cv2.resize(native, (int(160 * gb_scale), int(144 * gb_scale)),
                    interpolation=cv2.INTER_NEAREST)
    top = np.zeros((240, 400, 3), np.uint8)
    y, x = (240 - gb.shape[0]) // 2, (400 - gb.shape[1]) // 2
    top[y:y + gb.shape[0], x:x + gb.shape[1]] = gb
    return cv2.resize(top, (1600, 960), interpolation=cv2.INTER_NEAREST)


class FakeShared:
    """Stands in for SharedFrameCapture: frame(), frame_index(), last_index."""

    def __init__(self):
        self.lock = threading.Lock()
        self.index, self.picture, self.t = 0, np.zeros((960, 1600, 3), np.uint8), 0.0
        self.last_index = 0

    def publish(self, picture, t):
        with self.lock:
            self.index += 1
            self.picture, self.t = picture, t

    def frame(self):
        with self.lock:
            self.last_index = self.index
            return self.picture

    def frame_index(self):
        with self.lock:
            return self.index


class SimClock:
    """frame_recorder's clock, driven by the simulated stream."""

    def __init__(self, src):
        self.src = src

    def time(self):
        return self.src.t

    def sleep(self, s):
        real_time.sleep(min(s, 0.001))


def run(shiny, seed, gb_scale=1.5, gap=(0.025, 0.045)):
    rng = np.random.default_rng(seed)
    seq = []
    for n, f, phase in sim_battle.frames(shiny, rng):
        seq.append((n / FPS, f))
        if phase not in ("overworld", "transition", "black") and gb_screen.battle_text_shown(f):
            break
    src = FakeShared()
    frame_recorder.time = SimClock(src)
    rec = frame_recorder.RecordingCapture(src)
    try:
        rec.clear()
        t, end = rng.uniform(0, 0.02), seq[-1][0]
        while t <= end:
            k = min(int(t * FPS), len(seq) - 1)
            before = len(rec.recorder.stats)
            src.publish(top_screen(seq[k][1], gb_scale), t)
            deadline = real_time.time() + 2.0
            while len(rec.recorder.stats) == before and real_time.time() < deadline:
                real_time.sleep(0.0005)
            assert len(rec.recorder.stats) == before + 1, "a published frame wasn't recorded"
            t += rng.uniform(*gap)
        return rec.analyse()
    finally:
        rec.close()
        frame_recorder.time = real_time


def test_shared_frames_through_recorder():
    for scale in (1.0, 1.5):
        for seed in range(3):
            r = run(True, seed, scale)
            assert r["verdict"] == "shiny", (scale, seed, r)
            r = run(False, 1000 + seed, scale)
            assert r["verdict"] == "normal", (scale, seed, r)


def test_slow_stream_is_unsure_not_normal():
    for seed in range(3):
        r = run(True, seed, gap=(0.10, 0.15))
        assert r["verdict"] in ("shiny", "unsure"), (seed, r)
        r = run(False, 1000 + seed, gap=(0.10, 0.15))
        assert r["verdict"] == "unsure", (seed, r)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name}: ok")
