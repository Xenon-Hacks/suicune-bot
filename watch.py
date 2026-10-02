"""
watch.py -- react to the stream as fast as it updates, instead of fixed
waits.

The rule that keeps this safe: a stale stream frame can only ever show an
OLDER screen than the real one. So after pressing a button, the bot waits
until it has seen the OLD screen at least once and then the NEW screen on
two looks in a row. A "new" screen that appears after an "old" one must
be fresh -- it can't be left over from before the press.

Measured from a real 99-second recording of a human doing 5 Sweet Scent
encounters (the game's own timings, which nothing can speed up):
  START menu usable ............ 0.25 s after START
  party screen loaded .......... 0.6 s after A on POKEMON
  Sweet Scent message printed .. 1.1 s after A on SWEET SCENT
  "Wild X appeared!" -> menu ... 4.2 s after that text is cleared
  RUN -> "Got away safely!" .... 1.2 s
  "Got away" -> overworld ...... 0.95 s after it's cleared
"""

import threading
import time

import cv2
import numpy as np

import ntr_status

POLL = 0.05          # look at the stream ~15-20 times a second
HOLD = 0.2           # longer presses: in a real run 0.10 s presses were
                     # lost ~50% of the time and 0.15 s ones ~30%
RESEND = 6           # re-send the pressed state often during the hold
CONFIRM_SPAN = 0.2   # "confirmed" = true on every look for this long. NTR
                     # sends a new picture as soon as something changes, and
                     # the fastest double cursor move seen was 0.1 s, so a
                     # cursor passing THROUGH an item can't count as on it.
RETRY_AFTER = 1.0    # never repeat a press sooner than this. Measured on the
                     # START menu (test_menu_input.py, 45 presses): every
                     # press that landed showed up within 0.45 s; the rest
                     # were lost outright, never late.
STILL_DIFF = 1.0     # NTR's lossless stream: a still screen differs by 0.00,
                     # a fade by 6-17, the party icon bounce by 0.24
CONTENT_MIN = 6.0    # central-patch variation: fades/transitions 0.0-2.2,
                     # every real screen 13+ (night overworld 13.1)


_busy = None          # the press currently being held, if any


def _wait_idle():
    global _busy
    if _busy is not None:
        _busy.join()
        _busy = None


def tap(pad, button, name, log=True):
    """Starts a press and returns right away, so the bot can watch the
    screen WHILE the button is still held -- the game reacts on the first
    frame of the press, so waiting for the release first wasted ~0.2 s on
    every step. Presses never overlap: the next one always waits for this
    one to finish."""
    global _busy
    if ntr_status.is_down():
        # NTR Viewer reads 0%: the picture may be stale, so never press
        # blind. The bot treats this like a lost press and tries later.
        print(f"  (skipped {name}: NTR Viewer picture can't be trusted right now)", flush=True)
        return
    if log:
        print(f"  -> {name}", flush=True)
    _start_press(pad, button)


def _start_press(pad, button):
    """Sends one press in the background (the next press waits for it)."""
    global _busy
    _wait_idle()
    raw_tap = getattr(pad, "_raw_tap", pad.tap)
    _busy = threading.Thread(target=raw_tap, args=(button,),
                             kwargs=dict(hold=HOLD, gap=0.06, resend=RESEND), daemon=True)
    _busy.start()


def install(pad):
    """Makes every other button action on `pad` (pad.tap from the slower
    code paths, release_all, return_control, close) first wait for any
    press still being held, so two things never send at once."""
    if hasattr(pad, "_raw_tap"):
        return
    pad._raw_tap = pad.tap
    def serialized(f):
        def run(*a, **k):
            _wait_idle()
            return f(*a, **k)
        return run
    raw_serialized = serialized(pad._raw_tap)
    def guarded_tap(*a, **k):
        if ntr_status.is_down():          # same guard for the slower paths
            print("  (skipped a press: NTR Viewer picture can't be trusted right now)", flush=True)
            return
        return raw_serialized(*a, **k)
    pad.tap = guarded_tap
    for name in ("release_all", "return_control", "close"):
        setattr(pad, name, serialized(getattr(pad, name)))


def watch(cap, test, timeout, hold_for=None, before=None, heartbeat=None):
    """Polls the stream until test(frame) has been true on EVERY look for
    `hold_for` seconds (default CONFIRM_SPAN, and at least two looks) --
    so a single frame caught mid-change, like the cursor passing through
    POKEMON on its way to PACK, can never count. If `before` (the frame
    from just before a button press) is given and test(before) was
    already true, the test must first be seen FALSE -- so a leftover
    frame can never satisfy it. Returns the last frame, or None."""
    hold_for = CONFIRM_SPAN if hold_for is None else hold_for
    seen_false = True if before is None else not test(before)
    true_since, looks = None, 0
    end = time.time() + timeout
    while time.time() < end:
        if heartbeat:
            heartbeat()
        frame = cap.frame()
        now = time.time()
        if test(frame) and seen_false:
            if true_since is None:
                true_since, looks = now, 0
            looks += 1
            if looks >= 2 and now - true_since >= hold_for:
                return frame
        else:
            if not test(frame):
                seen_false = True
            true_since = None
        time.sleep(POLL)
    return None


def holds(cap, test, span=None, heartbeat=None):
    """Looks for `span` seconds; returns (True, frame) only if test() was
    true on every look -- (False, frame) as soon as one look fails."""
    span = CONFIRM_SPAN if span is None else span
    end = time.time() + span
    frame = cap.frame()
    while True:
        if heartbeat:
            heartbeat()
        if not test(frame):
            return False, frame
        if time.time() >= end:
            return True, frame
        time.sleep(POLL)
        frame = cap.frame()


def _gray_small(frame):
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (160, max(1, int(160 * g.shape[0] / g.shape[1]))),
                      interpolation=cv2.INTER_AREA).astype(np.float32)


def frames_differ(a, b, threshold=4.0):
    """True if two frames differ by more than stream noise (e.g. a text
    box clearing and the HP box appearing)."""
    return float(np.mean(np.abs(_gray_small(a) - _gray_small(b)))) > threshold


def screen_has_content(frame):
    """False for the flat screens shown during fades and transitions.
    Measured on a central patch, which is always inside the game picture:
    on the whole capture, NTR Viewer's black side bars made a flat fade
    look MORE detailed than the night-time overworld."""
    g = _gray_small(frame)
    h, w = g.shape
    core = g[int(h * 0.2):int(h * 0.8), int(w * 0.35):int(w * 0.65)]
    return float(np.std(core)) > CONTENT_MIN


def wait_still(cap, still_for, timeout, heartbeat=None):
    """Waits until the screen shows real content (not a fade) and has not
    changed at all for `still_for` seconds -- long enough to span several
    frames of a 4 FPS stream. Returns the frame, or None on timeout."""
    anchor, since = None, None
    end = time.time() + timeout
    while time.time() < end:
        if heartbeat:
            heartbeat()
        frame = cap.frame()
        now = time.time()
        if not screen_has_content(frame):
            anchor = None
        elif anchor is None or frames_differ(frame, anchor, STILL_DIFF):
            anchor, since = frame, now
        elif now - since >= still_for:
            return frame
        time.sleep(POLL)
    return None
