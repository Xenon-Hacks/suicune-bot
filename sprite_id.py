"""
sprite_id.py -- identify the wild Pokemon and decide shiny/normal by
comparing it with reference sprites (NORMAL/ and SHINY/ folders, one PNG
per species, same file name in both).

Every Game Boy Color sprite uses exactly four colours: white (the
background), black (the outline), and a light and a dark colour. A shiny
has the SAME pixels with a different light/dark pair. So:

  species -- the silhouette and the black outline pattern (identical for
             normal and shiny) compared against all references;
  shiny   -- the average captured colour of the sprite's "light" pixels and
             of its "dark" pixels, compared with that species' normal and
             shiny palettes. Averaging hundreds of pixels cancels out noise.

Colours are normalised first (the battle background counts as white, the
outline as black), because the picture's brightness varies between
sessions -- in real screenshots from the same setup the battle background
was grey in some and white in others.
"""

import os

import cv2
import numpy as np

GB_W, GB_H = 160, 144
ORIGIN = (96, 0)            # Crystal's 56x56 wild-Pokemon box, in native pixels
BOX_SIZE = 56
SLACK = 2                   # +-2 pixel alignment search around the known spot


def _sprite_offset(size):
    """Where Crystal draws a front sprite of this size inside its box:
    bottom-aligned, one tile (8 px) in from the left if smaller than the
    box. Measured on 15 real battles: 40x40 sprites at (8, 16), 48x48 at
    (8, 8); 56x56 sprites fill the box."""
    return (0 if size >= BOX_SIZE else 8), BOX_SIZE - size


def _load_canvas(path):
    """A reference sprite placed in a white 56x56 box exactly as the game
    places it (BGR, float)."""
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    h, w = im.shape[:2]
    canvas = np.full((BOX_SIZE, BOX_SIZE, 3), 255, np.uint8)
    ox, oy = _sprite_offset(max(h, w))
    canvas[oy:oy + h, ox:ox + w] = im[:BOX_SIZE - oy, :BOX_SIZE - ox]
    return canvas.astype(np.float32)


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


# --------------------------------------------------------------- references
def _load_reference(path):
    im = _load_canvas(path)
    colours = np.unique(im.reshape(-1, 3), axis=0)
    order = colours[np.argsort(-colours.mean(axis=1))]       # white, light, dark, black
    classes = np.zeros(im.shape[:2], np.uint8)
    for i, c in enumerate(order):
        classes[np.all(im == c, axis=2)] = i
    return {"classes": classes, "palette": order / 255.0}


class SpriteLibrary:
    def __init__(self, normal_dir, shiny_dir, skip=("UNOWN",)):
        def index(d):
            return {os.path.splitext(f)[0].upper(): os.path.join(d, f)
                    for f in os.listdir(d) if f.lower().endswith(".png")}
        n, s = index(normal_dir), index(shiny_dir)
        self.names = sorted(k for k in n if k in s and not k.startswith(skip))
        self.normal = {k: _load_reference(n[k]) for k in self.names}
        self.shiny = {k: _load_reference(s[k]) for k in self.names}
        for k in self.names:
            ref = self.normal[k]
            c = ref["classes"]
            ref["mask"] = c > 0
            ref["black"] = c == 3
            ref["mask32"] = ref["mask"].astype(np.float32)
            ref["black32"] = ref["black"].astype(np.float32)
            ref["mask_sum"] = float(ref["mask"].sum())
            ref["black_sum"] = float(ref["black"].sum())
            # "interior" pixels: same class as all 8 neighbours, so edges
            # (where scaling can blend colours) are left out
            same = np.ones_like(c, dtype=bool)
            p = np.pad(c, 1, mode="edge")
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    same &= p[1 + dy:1 + dy + c.shape[0], 1 + dx:1 + dx + c.shape[1]] == c
            for cls, key in ((1, "inner_light"), (2, "inner_dark")):
                inner = same & (c == cls)
                # small or thin sprites (e.g. Magnemite) may have almost no
                # interior pixels -- then use every pixel of that colour
                ref[key] = inner if inner.sum() >= 15 else (c == cls)
            # The shiny's colours, read at the SAME pixels as the normal
            # sprite's light and dark ones: for some species the shiny
            # palette swaps which colour is the brighter one.
            sh = _load_canvas(s[k]) / 255.0
            ref["shiny_at"] = {cls: np.median(sh[c == cls], axis=0) if (c == cls).any() else None
                               for cls in (1, 2)}

        self.size = self.normal[self.names[0]]["classes"].shape
        self.stack_mask = np.stack([self.normal[k]["mask32"].ravel() for k in self.names], axis=1)
        self.stack_black = np.stack([self.normal[k]["black32"].ravel() for k in self.names], axis=1)
        self.sum_mask = self.stack_mask.sum(axis=0)
        self.sum_black = self.stack_black.sum(axis=0)

    # ------------------------------------------------------------------
    def _window(self, native):
        h, w = self.size
        x0, y0 = ORIGIN[0] - SLACK, ORIGIN[1] - SLACK
        pad = SLACK + 2
        big = cv2.copyMakeBorder(native, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        win = big[y0 + pad:y0 + pad + h + 2 * SLACK, x0 + pad:x0 + pad + w + 2 * SLACK].astype(np.float32)
        flat = win.reshape(-1, 3)
        lum = flat.mean(axis=1)
        white = np.median(flat[lum >= np.percentile(lum, 60)], axis=0)   # battle background
        black = np.median(flat[lum <= np.percentile(lum, 3)], axis=0)    # outline
        norm = np.clip((win - black) / np.maximum(white - black, 1.0), 0.0, 1.0)
        nl = norm.mean(axis=2)
        return norm, (np.abs(norm - 1.0).max(axis=2) > 0.15), nl < 0.25

    def identify(self, native):
        norm, mask, black = self._window(native)
        h, w = self.size
        shifts = [(dx, dy) for dy in range(2 * SLACK + 1) for dx in range(2 * SLACK + 1)]
        M = np.stack([mask[dy:dy + h, dx:dx + w].ravel() for dx, dy in shifts]).astype(np.float32)
        B = np.stack([black[dy:dy + h, dx:dx + w].ravel() for dx, dy in shifts]).astype(np.float32)
        inter = M @ self.stack_mask                      # (shifts, species)
        inter_b = B @ self.stack_black
        iou_m = inter / np.maximum(M.sum(axis=1, keepdims=True) + self.sum_mask - inter, 1.0)
        iou_b = inter_b / np.maximum(B.sum(axis=1, keepdims=True) + self.sum_black - inter_b, 1.0)
        score = 0.5 * iou_m + 0.5 * iou_b
        best_shift = score.argmax(axis=0)                 # per species
        best = score[best_shift, np.arange(len(self.names))]
        order = np.argsort(-best)
        scores = [(float(best[i]), self.names[i], shifts[best_shift[i]]) for i in order[:2]]
        score, name, (ox, oy) = scores[0]
        ref = self.normal[name]
        h, w = ref["mask"].shape
        cap = norm[oy:oy + h, ox:ox + w]
        seen = {}
        for cls, key in ((1, "inner_light"), (2, "inner_dark")):
            px = cap[ref[key]]
            seen[cls] = (px.mean(axis=0), len(px)) if len(px) else (None, 0)

        GAMMAS = np.arange(0.5, 2.01, 0.05)

        def palette_distance(pal, gammas=None):
            """How well this palette explains the colours seen, allowing one
            midtone curve (the same for all channels -- a monitor or stream
            setting bends midtones, it doesn't know which Pokemon it is)."""
            best = None
            for g in (GAMMAS if gammas is None else gammas):
                total, weight = 0.0, 0
                for cls in (1, 2):
                    mean, n = seen[cls]
                    if n and pal[cls] is not None:
                        total += np.linalg.norm(mean - np.power(pal[cls], g)) * n
                        weight += n
                d = total / max(weight, 1)
                best = d if best is None or d < best else best
            return best

        d_normal = palette_distance(self.normal[name]["palette"])
        d_shiny = palette_distance(self.normal[name]["shiny_at"])

        # Position between the two palettes: 0 = exactly the normal colours,
        # 1 = exactly the shiny colours. Only error in the normal->shiny
        # direction counts, so a general tint or blur barely moves it.
        t_linear = None
        num, den = 0.0, 0.0
        for cls in (1, 2):
            mean, n = seen[cls]
            pn, ps = self.normal[name]["palette"][cls], self.normal[name]["shiny_at"][cls]
            if n and ps is not None:
                d = ps - pn
                num += n * float(np.dot(mean - pn, d))
                den += n * float(np.dot(d, d))
        t_linear = num / den if den > 1e-9 else 0.0
        return {"species": name, "score": score, "runner_up": scores[1][1], "runner_up_score": scores[1][0],
                "normal_dist": d_normal, "shiny_dist": d_shiny, "shiny": d_shiny < d_normal,
                "position": t_linear}


# ---------------------------------------------------------- battle readiness
TEXT_INK = 0.02        # share of dark pixels in the text box's text lines.
                       # Measured on real frames: empty box (mid-intro) 0.000,
                       # "Wild X appeared!" 0.057-0.074.


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
    return float((norm < 0.5).mean()) >= TEXT_INK


# ------------------------------------------------------------------ verdict
UNKNOWN_SCORE = 0.47   # best shape score below this = not a known Pokemon.
                       # Correct species scored >= 0.65 on real screenshots and
                       # >= 0.58 in 3,000 simulated captures; Unown (not in
                       # the library) never scored above 0.38.
SHINY_POSITION = 0.45  # possible shiny if the colours are at least this far
                       # from the normal palette towards the shiny one (0 = normal,
                       # 1 = shiny). Tested: normals <= +0.21 (simulated) and
                       # <= +0.34 (real); shinies >= +0.62, when colours are
                       # captured straight (as your screenshots are).
CURVE_RATIO = 1.2      # ...or if, allowing the capture to bend midtones, the
                       # normal palette explains the colours less than 1.2x
                       # better than the shiny one. Catches shinies when the
                       # colours ARE bent. Together: 0 missed shinies in 3,000
                       # simulated cases; real normals at x1.6 or more.


def find_sprite_folders(base):
    """NORMAL and SHINY folders inside `base` (any capitalisation)."""
    found = {}
    for entry in os.listdir(base):
        if os.path.isdir(os.path.join(base, entry)) and entry.upper() in ("NORMAL", "SHINY"):
            found[entry.upper()] = os.path.join(base, entry)
    return found.get("NORMAL"), found.get("SHINY")


def verdict(result):
    """'normal', 'shiny' (the shiny palette fits better), 'unsure' (too
    close to call -- treated like a possible shiny) or 'unknown' (not in
    the library)."""
    if result["score"] < UNKNOWN_SCORE:
        return "unknown"
    ratio = result["shiny_dist"] / max(result["normal_dist"], 1e-6)
    if result["position"] < SHINY_POSITION and ratio >= CURVE_RATIO:
        return "normal"
    return "shiny" if result["shiny_dist"] < result["normal_dist"] else "unsure"


def classify(library, frame_bgr):
    """Everything the bot needs from one battle frame."""
    result = library.identify(to_native(frame_bgr))
    result["verdict"] = verdict(result)
    result["ratio"] = result["shiny_dist"] / max(result["normal_dist"], 1e-6)
    return result
