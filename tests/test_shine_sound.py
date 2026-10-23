"""The shine-sound detector against synthetic audio: the 8 x SFX_SHINE
sequence mixed into square-wave 'music' must score well above music alone,
also after 32728 Hz streaming and with a 120 ms dropout."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shine_sound  # noqa: E402

SR = 48000


def music(seconds, seed):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(int(seconds * 8)):            # 8 notes a second
        n = SR // 8
        t = np.arange(n) / SR
        chord = sum(np.sign(np.sin(2 * np.pi * f * t))
                    for f in rng.choice([131, 165, 196, 262, 330, 392, 523, 659, 784], 3))
        out.append(chord / 3)
    return np.concatenate(out).astype(np.float32) * 0.3


def with_shine(x, at, scale=0.25, hole=False):
    s = shine_sound.synth(SR) * scale
    y = x.copy()
    i = int(at * SR)
    y[i:i + len(s)] += s
    if hole:
        h = i + int(0.3 * SR)
        y[h:h + int(0.12 * SR)] = 0
    return y


def test_music_alone_scores_low():
    for seed in range(3):
        score, _ = shine_sound.best_match(music(6, seed), SR)
        assert score < 0.15, score


def test_shine_scores_high_and_is_located():
    x = music(6, 7)
    score, at = shine_sound.best_match(with_shine(x, 2.0), SR)
    assert score > 0.3, score
    assert abs(at - 2.0) < 0.05, at


def test_shine_survives_a_dropout():
    score, _ = shine_sound.best_match(with_shine(music(6, 8), 2.5, hole=True), SR)
    assert score > 0.25, score
