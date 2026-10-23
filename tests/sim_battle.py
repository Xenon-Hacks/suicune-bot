"""
sim_battle.py -- a stand-in for the game, for testing without a ROM or any
Pokemon graphics. It draws random blobs in Game Boy Color style (four shades
per palette, black outlines) and replays the frame sequence Crystal shows
around a wild battle start, as traced in the pokecrystal decompile:

  overworld -> transition (palette flashes, then a wipe to all-black) ->
  battle screen with both pictures sliding in -> [shiny only: 5 frames of
  the battle field's palette reversed, then ~64 frames of sparkles] -> the Pokemon's own
  animation -> HP box + "Wild X appeared!" text.

frames(shiny, rng) yields (frame_number, 160x144 BGR image, phase).
"""

import numpy as np

W, H = 160, 144


def _palette(rng):
    """White, a light colour, a dark colour, black (BGR)."""
    light = rng.integers(120, 240, 3)
    dark = (light * rng.uniform(0.25, 0.6)).astype(int)
    return np.array([[248, 248, 248], light, dark, [16, 16, 16]], np.uint8)


def _blob(rng, size):
    """A random filled shape with a black outline, as shade indexes 0-3."""
    yy, xx = np.mgrid[0:size, 0:size]
    c = size / 2
    r = np.zeros((size, size))
    for _ in range(rng.integers(2, 5)):
        cx, cy = rng.uniform(c * 0.6, c * 1.4, 2)
        rad = rng.uniform(size * 0.15, size * 0.38)
        r = np.maximum(r, 1.0 - np.hypot(xx - cx, yy - cy) / rad)
    inside = r > 0
    idx = np.where(inside, 1, 0)
    idx[(r > 0) & (r < 0.25)] = 2
    edge = inside & ~(np.roll(inside, 1, 0) & np.roll(inside, -1, 0)
                      & np.roll(inside, 1, 1) & np.roll(inside, -1, 1))
    idx[edge] = 3
    return idx.astype(np.uint8)


class Scene:
    def __init__(self, rng):
        self.rng = rng
        self.enemy = _blob(rng, int(rng.choice([40, 48, 56])))
        self.player = _blob(rng, 48)
        self.enemy_pal = _palette(rng)
        self.player_pal = _palette(rng)
        self.gray = np.array([[248, 248, 248], [170, 170, 170], [90, 90, 90], [16, 16, 16]], np.uint8)
        self.overworld = rng.integers(0, 4, (H // 8, W // 8)).repeat(8, 0).repeat(8, 1).astype(np.uint8)
        self.ow_pal = _palette(rng)

    def overworld_frame(self, invert=False):
        idx = 3 - self.overworld if invert else self.overworld
        return self.ow_pal[idx]

    def battle(self, enemy_x=96, player_x=8, invert=False, hud=False, text=False,
               sparkles=0, anim_shift=0):
        """Shade-index layers with their palettes, composed into BGR."""
        idx = np.zeros((H, W), np.uint8)
        pal = np.zeros((H, W), np.uint8)       # 0 gray/text, 1 enemy, 2 player
        e = self.enemy
        eh, ew = e.shape
        ex, ey = enemy_x + (56 - ew) // 2 + anim_shift, 56 - eh
        self._paste(idx, pal, e, ex, ey, 1)
        p = self.player
        self._paste(idx, pal, p, player_x, 96 - p.shape[0], 2)
        # text box border, rows 96-143
        idx[96:144, 0:160][[0, 1, -2, -1], :] = 3
        idx[96:144, [0, 1, 158, 159]] = 3
        if hud:
            idx[16:18, 16:80] = 3
            idx[10:14, 8:60:3] = 3
        if text:
            rr = self.rng
            idx[112:120, 8:120] = np.where(rr.random((8, 112)) < 0.35, 3, idx[112:120, 8:120])
        if invert:
            # Game Boy Color: only the battle field's own palette reverses
            # (its white turns black); the Pokemon keep their colours and
            # the text box stays as it was -- as in the real game.
            field = (pal == 0)
            field[96:] = False
            idx = np.where(field, 3 - idx, idx)
        out = np.empty((H, W, 3), np.uint8)
        for k, palette in enumerate((self.gray, self.enemy_pal, self.player_pal)):
            m = pal == k
            out[m] = palette[idx[m]]
        for s in range(sparkles):
            ang = s * 0.8
            sx = int(124 + 30 * np.cos(ang))
            sy = int(28 + 26 * np.sin(ang))
            out[max(sy, 0):sy + 6, max(sx, 0):sx + 6] = (40, 220, 240)
        return out

    @staticmethod
    def _paste(idx, pal, img, x, y, k):
        h, w = img.shape
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, W), min(y + h, H)
        if x1 <= x0 or y1 <= y0:
            return
        sub = img[y0 - y:y1 - y, x0 - x:x1 - x]
        m = sub > 0
        idx[y0:y1, x0:x1][m] = sub[m]
        pal[y0:y1, x0:x1][m] = k


def frames(shiny, rng):
    """The whole battle start, one Game Boy frame (1/60 s) at a time."""
    sc = Scene(rng)
    n = 0
    for _ in range(int(rng.integers(30, 90))):
        yield n, sc.overworld_frame(), "overworld"; n += 1
    # transition: 3 palette flashes of the overworld (bright/dark/bright),
    # then the wipe, then all black for a while
    for _ in range(3):
        for inv in (True, True, True, True, False, False, False, False):
            yield n, sc.overworld_frame(invert=inv), "transition"; n += 1
    for k in range(40):
        f = sc.overworld_frame().copy()
        f[:int(H * (k + 1) / 40)] = 0
        yield n, f, "transition"; n += 1
    for _ in range(int(rng.integers(20, 60))):
        yield n, np.zeros((H, W, 3), np.uint8), "black"; n += 1
    # slide-in: enemy from the left, player from the right
    for k in range(70):
        t = (k + 1) / 70
        yield n, sc.battle(enemy_x=int(-56 + t * 152), player_x=int(160 - t * 152)), "slide"; n += 1
    for _ in range(10):
        yield n, sc.battle(), "battle"; n += 1
    if shiny:
        for _ in range(5):                  # FlashInverted: one reversed period
            yield n, sc.battle(), "battle"; n += 1
        for _ in range(5):
            yield n, sc.battle(invert=True), "flash"; n += 1
        for k in range(64):
            yield n, sc.battle(sparkles=min(8, k // 4 + 1)), "sparkle"; n += 1
    for k in range(int(rng.integers(40, 120))):  # the Pokemon's own animation
        yield n, sc.battle(anim_shift=int(2 * np.sin(k / 3))), "cry"; n += 1
    for _ in range(90):
        yield n, sc.battle(hud=True, text=True), "text"; n += 1


def to_capture(native, rng, scale=3, bars=40, noise=4.0, jpeg=True):
    """Roughly what a screen grab of NTR Viewer gives: scaled up, black
    bars at the sides, some noise and compression."""
    import cv2
    big = cv2.resize(native, (W * scale, H * scale), interpolation=cv2.INTER_NEAREST)
    big = cv2.copyMakeBorder(big, 0, 0, bars, bars, cv2.BORDER_CONSTANT, value=0)
    big = np.clip(big.astype(np.float32) + rng.normal(0, noise, big.shape), 0, 255).astype(np.uint8)
    if jpeg:
        ok, enc = cv2.imencode(".jpg", big, [cv2.IMWRITE_JPEG_QUALITY, 70])
        big = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return big
