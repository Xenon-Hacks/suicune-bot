"""
walk_menu.py -- the extra steps the walk-up variant needs between the
soft reset and the battle: mash A only until the saved overworld is back
on screen, take one step UP onto the event tile, then mash A through the
cutscene until the battle starts (reset_menu.mash_to_battle does that
last part, unchanged).

Matched against a recording of the Suicune encounter: the save loads
outside Tin Tower facing its door, ~7 s after the reset. One step UP
walks into the door (the screen fades to white within ~0.3 s), the
player is walked up inside on its own, and the battle screen shows ~16 s
after the step, "Wild SUICUNE appeared!" ~2.5 s after that.

Why the mash has to stop at the overworld: in the original static bot,
the save stands right in front of the Pokemon, so A can be mashed all the
way into the battle. Here the battle only starts after a step, and A
mashed on the overworld does nothing useful (at best) -- so the bot
watches for the exact overworld screen your save loads into (calibrated
as ref_overworld_start.png, see calibrate.py --overworld), stops pressing
A the moment it appears, and only then presses UP.

Safety notes:
  * UP is the only direction this module ever sends, and only after the
    saved overworld screen has been confirmed on several looks in a row
    and the screen has settled (fade-in finished).
  * Each UP press is checked: the bot only moves on once the whole
    screen has visibly changed (the camera scrolls a tile, or the
    cutscene starts). Turning on the spot only changes the player
    sprite, which isn't enough, so the bot presses UP again -- up to
    WALK_TRIES times, then gives up on the attempt. Stepping onto an
    event tile stops movement on its own, so a longer UP press can't
    carry the player past it.
  * Any failure here just ends the attempt; the next soft reset starts
    clean from the save, same as everywhere else in this bot.
"""

import glob
import time

import cv2

from luma_input import Button
from vision import crop
import ntr_status
import watch
from reset_menu import MASH_HOLD, MASH_INTERVAL, MASH_TIMEOUT

OVERWORLD_REF = "ref_overworld_start.png"
OVERWORLD_REF_GLOB = "ref_overworld_start*.png"   # extra ones from
                                  # calibrate.py --overworld-add: the saved
                                  # spot is outdoors (in front of Tin Tower,
                                  # in a test recording), so its colours change
                                  # with Crystal's morning/day/night clock.
                                  # The best match of all of them counts.
OVERWORLD_MATCH_THRESHOLD = 0.75  # watch the printed (overworld match: X.XX)
                                  # lines -- the saved spot should read well
                                  # above this, the title/CONTINUE screens
                                  # well below. Nudge it if it misfires.
OVERWORLD_CONFIRM = 0.25     # the overworld must match on every look for
                             # this long before the bot treats it as loaded.
                             # Was 0.5; in the log every non-overworld
                             # screen scores 0.00-0.08 against 0.75, so a
                             # shorter confirm can't mistake one. The
                             # settle-still wait below is unchanged.
OVERWORLD_SETTLE = 0.3       # then the screen must stay still this long
                             # (the map fade-in has finished, so the game
                             # is accepting input again)
WALK_HOLD = 0.25             # UP is held this long: enough for a turn plus
                             # the start of a step (one tile is 16 frames)
WALK_CONFIRM = 1.5           # how long to watch for the screen to change
                             # after each UP press
WALK_TRIES = 3               # UP presses before giving up on this attempt
WALK_DIFF = 4.0              # whole-screen change that counts as "moved"
                             # (a tile of scrolling or the cutscene); just
                             # turning to face UP stays well under this
CUTSCENE_TIMEOUT = 45.0      # ceiling for step -> cutscene -> battle
                             # (~16 s in a test recording)


_last_status_print = 0.0
_refs = None


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def overworld_score(frame, cfg):
    """Best match of the frame's overworld_roi against every saved start
    screen. Compared in grayscale: the time-of-day palettes mostly shift
    brightness, which normalised matching ignores, while the layout (tower,
    trees, door) is what tells this screen apart from the title/CONTINUE
    screens."""
    global _refs
    if _refs is None:
        _refs = [_gray(cv2.imread(p)) for p in sorted(glob.glob(OVERWORLD_REF_GLOB))]
        if not _refs:
            raise FileNotFoundError(f"{OVERWORLD_REF} not found -- run calibrate.py.")
    patch = _gray(crop(frame, cfg["overworld_roi"]))
    best = -1.0
    for ref in _refs:
        p = patch if patch.shape == ref.shape else cv2.resize(patch, (ref.shape[1], ref.shape[0]))
        best = max(best, float(cv2.matchTemplate(p, ref, cv2.TM_CCOEFF_NORMED).max()))
    return best


def on_overworld(cap, cfg, frame=None, log=True):
    """True if the saved starting spot is on screen. Prints the raw score
    every couple of seconds, like in_battle(), so a miscalibration is
    visible in the log instead of a silent timeout."""
    global _last_status_print
    frame = cap.frame() if frame is None else frame
    score = overworld_score(frame, cfg)
    result = score >= OVERWORLD_MATCH_THRESHOLD
    now = time.time()
    if log and now - _last_status_print > 2.0:
        flag = " [OVERWORLD]" if result else ""
        print(f"  (overworld match: {score:.2f}{flag})", flush=True)
        _last_status_print = now
    return result


def mash_to_overworld(pad, cap, cfg, in_battle, heartbeat=lambda: None,
                      timeout=MASH_TIMEOUT):
    """Mashes A through the boot logos, title screen, CONTINUE and the save
    summary, and stops the moment the saved overworld appears. Returns
    "overworld" once it's confirmed and settled, "battle" if a battle
    started on its own (the save is already past the event tile), or None
    on timeout."""
    start = time.time()
    end = start + timeout
    presses = 0
    while time.time() < end:
        heartbeat()
        if in_battle(cap, cfg):
            print(f"  Battle started during the reset mash after {presses} A "
                  f"presses -- no walk needed this time.", flush=True)
            return "battle"
        if on_overworld(cap, cfg):
            # No more A from here. Make sure it wasn't a passing frame,
            # then let the fade-in finish before anything else is pressed.
            ok, _ = watch.holds(cap, lambda f: on_overworld(cap, cfg, f, log=False),
                                span=OVERWORLD_CONFIRM, heartbeat=heartbeat)
            if ok:
                watch.wait_still(cap, OVERWORLD_SETTLE, 3.0, heartbeat=heartbeat)
                print(f"  Overworld loaded after {presses} A presses "
                      f"({time.time() - start:.1f}s).", flush=True)
                return "overworld"
            continue
        if ntr_status.is_down():
            # The picture may be stale -- never mash blind into a frozen
            # frame, just wait for the stream to come back.
            time.sleep(0.25)
            continue
        pad.tap(Button.A, hold=MASH_HOLD, gap=MASH_INTERVAL)
        presses += 1
    print(f"  Overworld never appeared after {presses} A presses over "
          f"{timeout:.0f}s -- giving up on this attempt.", flush=True)
    return None


def walk_up(pad, cap, heartbeat=lambda: None):
    """Presses UP until the screen visibly changes (the step happened, or
    the cutscene started). Returns True if it did, False after WALK_TRIES
    presses with no change."""
    for attempt in range(1, WALK_TRIES + 1):
        heartbeat()
        while ntr_status.is_down():
            heartbeat()
            time.sleep(0.25)
        before = cap.frame()
        print(f"  Walking one tile UP (press {attempt}/{WALK_TRIES})...", flush=True)
        pad.tap(Button.UP, hold=WALK_HOLD, gap=0.05, resend=6)
        moved = watch.watch(cap, lambda f: watch.frames_differ(f, before, WALK_DIFF),
                            WALK_CONFIRM, hold_for=0.1, heartbeat=heartbeat)
        if moved is not None:
            print("  Step taken -- waiting for the cutscene and battle.", flush=True)
            return True
    print(f"  The screen never changed after {WALK_TRIES} UP presses -- "
          f"giving up on this attempt.", flush=True)
    return False
