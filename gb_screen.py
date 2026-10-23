"""
gb_screen.py -- where the Game Boy picture sits inside a capture, how to
read it back at native 160x144, and whether the battle text box has text
in it. No Pokemon graphics are used or needed here.

(These helpers used to live in sprite_id.py, which also compared the
wild Pokemon against reference sprites. That sprite comparison is gone;
shininess now comes from the shiny animation, see shiny_flash.py.)
"""

import cv2
import numpy as np

GB_W, GB_H = 160, 144


# ------------------------------------------------------------------ capture
def _longest_run(mask):
    best, cur, start = (0, 0, 0), 0, 0
    for i, m in enumerate(mask):
        if m:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[0]:
                best = (cur, start, i + 1)
        else:
            cur = 0
    return best[1], best[2]


MIN_GAME_WIDTH = 40   # px; anything narrower isn't the game picture


def find_game(frame_bgr):
    """(x, y, w, h) of the Game Boy picture inside the capture: the widest
    bright column run (NTR Viewer adds black bars at the sides), with the
    height fixed by the Game Boy's 160x144 shape."""
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    x0, x1 = _longest_run(g.mean(axis=0) > 60)
    w = x1 - x0
    if w < MIN_GAME_WIDTH:
        # No bright game picture in this frame (a black/fading screen, e.g.
        # mid-reset or a stream dip). w = 0 used to make h = 0, and then
        # csum[:-0] is an EMPTY array -> "operands could not be broadcast
        # together with shapes (N,) (0,)" crashed the bot. Use the whole
        # frame instead; the callers then just see a dark, featureless
        # picture (no battle text, no recognisable sprite) and keep waiting.
        return 0, 0, g.shape[1], g.shape[0]
    h = min(round(w * GB_H / GB_W), g.shape[0])
    rows = g[:, x0 + 2:max(x0 + 3, x1 - 2)].mean(axis=1)
    csum = np.r_[0, np.cumsum(rows)]
    y0 = int(np.argmax(csum[h:] - csum[:-h])) if len(rows) > h else 0
    return x0, y0, w, h


def to_native(frame_bgr, game=None):
    """The game picture at Game Boy resolution, reading the CENTRE of each
    Game Boy pixel (averaging a small patch there) so edges don't blur."""
    x, y, w, h = game or find_game(frame_bgr)
    sx, sy = w / GB_W, h / GB_H
    r = max(1, int(min(sx, sy) * 0.25))
    blurred = cv2.blur(frame_bgr, (2 * r + 1, 2 * r + 1))
    cols = np.clip((x + (np.arange(GB_W) + 0.5) * sx).astype(int), 0, frame_bgr.shape[1] - 1)
    rows = np.clip((y + (np.arange(GB_H) + 0.5) * sy).astype(int), 0, frame_bgr.shape[0] - 1)
    return blurred[np.ix_(rows, cols)]


# ---------------------------------------------------------- battle readiness
TEXT_INK = 0.02        # share of dark pixels in the text box's text lines.
                       # Measured on real frames: empty box (mid-intro) 0.000,
                       # "Wild X appeared!" 0.057-0.074.
TEXT_INK_MAX = 0.35    # ...and at most this much: text is dark letters on a
                       # light box. During the shiny flash the whole box
                       # turns dark (~1.0), which must not count as text --
                       # stopping there would cut the flash off mid-way.


MIN_CONTRAST = 40.0    # white-vs-black spread of a real battle screen is
                       # far larger; a black/faded frame is ~0


def battle_text_shown(native):
    """True once the battle text box has text in it. In Crystal "Wild X
    appeared!" only prints AFTER the wild Pokemon has finished sliding
    in, so this means the sprite is fully displayed -- and a picture
    frozen mid-intro (as seen with a stalled stream) can never pass."""
    area = native[104:136, 8:152].astype(np.float32).mean(axis=2)
    lum = native.astype(np.float32).mean(axis=2)
    white, black = np.percentile(lum, 90), np.percentile(lum, 1)
    if white - black < MIN_CONTRAST:
        return False   # a flat (black/fading) screen has no text. Without
                       # this, an all-black frame counted as "text shown"
                       # (every pixel is 'dark' relative to itself).
    norm = (area - black) / max(white - black, 1.0)
    ink = float((norm < 0.5).mean())
    return TEXT_INK <= ink <= TEXT_INK_MAX


def native(frame_bgr):
    """Any capture of the game as a 160x144 picture. A frame that's already
    the Game Boy screen at native size or a whole-number scale of it (what
    BizHawk sends) is just scaled down; anything else (an NTR Viewer
    window with black bars) is located first with find_game()."""
    h, w = frame_bgr.shape[:2]
    if (w, h) == (GB_W, GB_H):
        return frame_bgr
    if w % GB_W == 0 and h % GB_H == 0 and w // GB_W == h // GB_H:
        return cv2.resize(frame_bgr, (GB_W, GB_H), interpolation=cv2.INTER_AREA)
    return to_native(frame_bgr)
