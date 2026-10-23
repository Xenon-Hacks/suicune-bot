"""
Checks shiny_flash.analyse() against simulated battle starts (see
sim_battle.py) -- no ROM and no Pokemon graphics involved.

    py -m pytest tests            (or: py tests/test_shiny_flash.py)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import gb_screen                     # noqa: E402
import shiny_flash                   # noqa: E402
import sim_battle                    # noqa: E402

FPS = 60.0


def _until_text(shiny, rng):
    """Every frame up to the first one the bots would take as "Wild X
    appeared!" showing (gb_screen.battle_text_shown, which the bots only
    start checking once the battle has started)."""
    for n, f, phase in sim_battle.frames(shiny, rng):
        yield n / FPS, f, phase
        if phase not in ("overworld", "transition", "black") and gb_screen.battle_text_shown(f):
            assert phase == "text", phase
            return


def run_exact(shiny, seed):
    rng = np.random.default_rng(seed)
    rec = shiny_flash.FlashRecorder()
    for t, f, _ in _until_text(shiny, rng):
        rec.add(t, f)
    return rec.analyse(frame_exact=True)


def run_captured(shiny, seed, gap=(0.025, 0.045), blend=0.3):
    """A ~30 fps capture of a ~60 fps game: frames picked at irregular
    times, sometimes two game frames blended (stream encoding), scaled
    into a window with black bars, with noise and JPEG artefacts."""
    rng = np.random.default_rng(seed)
    seq = list(_until_text(shiny, rng))
    rec = shiny_flash.FlashRecorder()
    t = rng.uniform(0, 0.02)
    end = seq[-1][0]
    while t <= end:
        k = min(int(t * FPS), len(seq) - 1)
        f = seq[k][1]
        if k + 1 < len(seq) and rng.random() < blend:
            f = ((f.astype(np.uint16) + seq[k + 1][1]) // 2).astype(np.uint8)
        cap = sim_battle.to_capture(f, rng)
        rec.add(t, gb_screen.native(cap))
        t += rng.uniform(*gap)
    return rec.analyse()


def test_frame_exact():
    for seed in range(30):
        assert run_exact(True, seed)["verdict"] == "shiny", seed
        assert run_exact(False, 1000 + seed)["verdict"] == "normal", seed


def test_captured_stream():
    for seed in range(6):
        r = run_captured(True, seed)
        assert r["verdict"] == "shiny", (seed, r)
        r = run_captured(False, 1000 + seed)
        assert r["verdict"] == "normal", (seed, r)


def test_slow_capture_never_says_normal_for_a_shiny():
    # 100-150 ms between frames can step right over a 83 ms flash; that
    # must come out as "unsure" (the bot stops), never "normal".
    for seed in range(6):
        r = run_captured(True, seed, gap=(0.10, 0.15))
        assert r["verdict"] in ("shiny", "unsure"), (seed, r)


def test_no_transition_seen_is_unsure():
    rng = np.random.default_rng(5)
    rec = shiny_flash.FlashRecorder()
    for t, f, phase in _until_text(False, rng):
        if phase in ("slide", "battle", "cry", "text"):
            rec.add(t, f)
    assert rec.analyse(frame_exact=True)["verdict"] == "unsure"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name}: ok")
