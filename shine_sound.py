"""
shine_sound.py -- spots the shiny animation by its sound. A shiny wild
Pokemon's animation plays SFX_SHINE eight times (pokecrystal:
data/moves/animations.asm, BattleAnim_SendOutMon.Shiny; audio/sfx.asm,
Sfx_Shine_Ch5): a 12.5%-duty square wave stepping 512 -> 683 -> 1024 ->
2048 -> 4096 Hz one game frame per step, restarted every 5 frames, with
the last 4096 Hz note left ringing for 11 frames -- about 0.8 s in all.
Nothing else in a wild battle sounds like it. The detector slides a
spectrogram of that exact sound along the game audio and reports the
best match (normalised correlation, 0..1).
"""

import numpy as np

FPS = 59.7275
GB_FREQS = [512, 683, 1024, 2048]      # 131072 / (2048 - x) for x = 1792..1984
RING = 4096                            # x = 2016
WIN = 0.012                            # s, spectrogram window
HOP = 0.004                            # s
F_LO, F_HI = 400.0, 9000.0


def synth(sr):
    """The 8 x SFX_SHINE sequence as the Game Boy plays it (one channel)."""
    frames = []
    for rep in range(8):
        steps = GB_FREQS + [RING] * (1 if rep < 7 else 11)
        frames += steps
    n = int(round(sr / FPS))
    out, phase = [], 0.0
    for f in frames:
        t = phase + np.arange(n) * f / sr
        out.append(np.where((t % 1.0) < 0.125, 1.0, -0.14))
        phase = (phase + n * f / sr) % 1.0
    return np.concatenate(out).astype(np.float32)


def spectrogram(x, sr):
    n = int(round(WIN * sr))
    h = int(round(HOP * sr))
    if len(x) < n:
        return np.zeros((0, 0), np.float32)
    idx = np.arange(0, len(x) - n + 1, h)[:, None] + np.arange(n)[None, :]
    seg = x[idx] * np.hanning(n).astype(np.float32)
    sp = np.abs(np.fft.rfft(seg, axis=1))
    fr = np.fft.rfftfreq(n, 1 / sr)
    keep = (fr >= F_LO) & (fr <= F_HI)
    s = np.log1p(sp[:, keep] / (np.abs(x).max() + 1e-9) * 100)
    # Whiten each column over time so steady music notes count less.
    s -= s.mean(axis=1, keepdims=True)
    return s.astype(np.float32)          # (time, freq)


_templates = {}


def template(sr):
    if sr not in _templates:
        _templates[sr] = spectrogram(synth(sr), sr)
    return _templates[sr]


def best_match(x, sr):
    """Highest normalised correlation of the SFX_SHINE template anywhere in
    mono audio x, and the time (s) it starts at."""
    T = template(sr)
    S = spectrogram(np.asarray(x, np.float32), sr)
    if S.shape[0] < T.shape[0]:
        return 0.0, None
    L = T.shape[0]
    t = (T - T.mean()).ravel()
    t /= np.linalg.norm(t) + 1e-9
    best, at = -1.0, None
    for i in range(0, S.shape[0] - L + 1):
        w = S[i:i + L]
        w = (w - w.mean()).ravel()
        c = float(w @ t) / (np.linalg.norm(w) + 1e-9)
        if c > best:
            best, at = c, i * HOP
    return best, at
