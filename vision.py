"""
vision.py

Screen-capture based helpers for detecting battle transitions, the Ditto
species, and shininess, used by sweet_scent_bot.py.

Everything here reads pixels off wherever the NTR Viewer window sits on
YOUR screen (see calibrate.py) -- it does not talk to the NTR video stream
protocol directly, so NTR Viewer needs to be visible (not minimized,
not covered by another window) while the bot runs.
"""

import time

import cv2
import numpy as np
import mss


class Capture:
    def __init__(self, region: dict):
        """region = {"left": int, "top": int, "width": int, "height": int}
        -- the on-screen pixel rectangle occupied by NTR Viewer's game
        view. Produced by calibrate.py."""
        self.region = region

    def frame(self) -> np.ndarray:
        """Returns a BGR numpy array (OpenCV convention). Opens a fresh
        mss() each call -- mss isn't reliably thread/handle-safe held open
        across a long-running loop on all platforms."""
        with mss.mss() as sct:
            shot = sct.grab(self.region)
            img = np.array(shot)  # BGRA
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def wait_until_stable(cap: Capture, samples: int = 3, interval: float = 0.35,
                       max_wait: float = 6.0, diff_threshold: float = 3.0) -> np.ndarray:
    """Waits until the screen stops visibly changing -- i.e. an intro
    animation or typewriter-effect text has finished rendering -- rather
    than guessing a fixed delay. Gives up and returns the latest frame
    anyway after `max_wait` seconds so a stuck loop never hangs forever.
    Returns the final (settled, or last-seen) frame."""
    start = time.time()
    prev = None
    stable_count = 0
    frame = cap.frame()
    while time.time() - start < max_wait:
        frame = cap.frame()
        if prev is not None:
            diff = float(np.mean(cv2.absdiff(frame, prev)))
            if diff < diff_threshold:
                stable_count += 1
                if stable_count >= samples:
                    return frame
            else:
                stable_count = 0
        prev = frame
        time.sleep(interval)
    return frame


def crop(frame: np.ndarray, roi: dict) -> np.ndarray:
    """roi = {"left":, "top":, "width":, "height":}, relative to `frame`."""
    x, y, w, h = roi["left"], roi["top"], roi["width"], roi["height"]
    return frame[y:y + h, x:x + w]


def match_score(frame: np.ndarray, roi: dict, reference_path: str) -> float:
    """Raw normalized template-match score (0-1, higher = closer match) of
    `frame` cropped to `roi` against a saved reference image."""
    ref = cv2.imread(reference_path)
    if ref is None:
        raise FileNotFoundError(
            f"{reference_path} not found -- did calibrate.py finish?")
    patch = crop(frame, roi)
    if patch.shape[:2] != ref.shape[:2]:
        patch = cv2.resize(patch, (ref.shape[1], ref.shape[0]))
    result = cv2.matchTemplate(patch, ref, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return float(score)


def looks_like(frame: np.ndarray, roi: dict, reference_path: str,
                threshold: float = 0.85) -> bool:
    """True if `frame`'s `roi` scores at or above `threshold` against a
    saved reference image."""
    return match_score(frame, roi, reference_path) >= threshold


def is_ditto(frame: np.ndarray, sprite_roi: dict, template_path: str,
             threshold: float = 0.75) -> bool:
    """Shape/outline match against a saved Ditto sprite crop. Shininess
    doesn't change Ditto's silhouette, only its color, so one template
    (captured from either a normal or shiny encounter) covers both."""
    return looks_like(frame, sprite_roi, template_path, threshold)


def average_hue(frame: np.ndarray, sprite_roi: dict) -> float:
    """Mean HSV hue (OpenCV's 0-179 scale) of the saturated pixels in the
    sprite region -- i.e. ignoring near-white/near-black/low-saturation
    pixels like outlines, background, and HP-bar text, which would
    otherwise dilute the average toward gray."""
    patch = crop(frame, sprite_roi)
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    mask = hsv[:, :, 1] > 60  # saturation threshold
    hues = hsv[:, :, 0][mask]
    if hues.size == 0:
        return -1.0
    return float(np.mean(hues))


# In Generation II, normal Ditto is pink/magenta and shiny Ditto is blue.
# On OpenCV's 0-179 hue scale, magenta/pink sits roughly 140-179 (wrapping
# to ~0-10), blue sits roughly 95-130. This range is a starting point, not
# something tested against your specific capture/compression settings --
# see the README for how to tune it if it misfires.
SHINY_HUE_RANGE = (95, 130)


def is_shiny_ditto(frame: np.ndarray, sprite_roi: dict) -> bool:
    hue = average_hue(frame, sprite_roi)
    if hue < 0:
        return False
    lo, hi = SHINY_HUE_RANGE
    return lo <= hue <= hi
