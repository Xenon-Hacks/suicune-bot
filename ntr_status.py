"""
ntr_status.py -- reads NTR Viewer's window title to tell whether the
stream from the 3DS is still alive. When the 3DS freezes or disconnects,
NTR Viewer keeps showing the LAST picture it received, so the bot would
otherwise keep pressing buttons at a frozen image. The title says so
directly, e.g.:
    NTRViewer-HR (FPS 000/000) (Connection Quality 0.0%) [Lossless RS, Delta]
Windows only; on anything else (or if the window can't be found) it
reports "unknown" and the bot carries on as before.
"""

import re
import sys
import time

_QUALITY = re.compile(r"Connection Quality\s*([\d.]+)\s*%")


TITLE_PREFIXES = ("NTRViewer", "NTR-VC")


def _windows():
    """NTR Viewer / NTR-VC windows: a list of dicts with title, hung
    (Windows reports it "Not Responding") and minimised. Empty if none
    or not on Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each_window(hwnd, _lparam):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value.startswith(TITLE_PREFIXES):
                    found.append({"title": buf.value,
                                  "hung": bool(user32.IsHungAppWindow(hwnd)),
                                  "minimised": bool(user32.IsIconic(hwnd))})
            return True

        user32.EnumWindows(each_window, 0)
        return found
    except Exception:
        return []


def ntr_title():
    """The viewer's title (a responding window's, if there's a choice)."""
    wins = _windows()
    for w in wins:
        if not w["hung"] and "(Not Responding)" not in w["title"]:
            return w["title"]
    return wins[0]["title"] if wins else None


shared_source = None     # set by the bot when it reads frames from the
                         # frame-sharing viewer (shared_frame.py)


def connection_quality(title=None):
    """NTR Viewer's reported connection quality in percent, or None if
    unknown (not Windows, window not found, title not recognised). With
    the frame-sharing viewer it comes from shared memory, which keeps
    working while the window is minimised."""
    if title is None and shared_source is not None:
        q = shared_source.quality()
        if q is not None:
            return q
    title = ntr_title() if title is None else title
    if not title:
        return None
    m = _QUALITY.search(title)
    return float(m.group(1)) if m else None


FREEZE_AFTER = 30.0   # seconds at 0% before it counts as a real freeze.
                      # NTR Viewer briefly reads 0% during battle
                      # transitions even when the 3DS is fine (seen twice in
                      # a 3-hour run); a frozen 3DS never comes back.


def wait_for_good_quality(minimum=50.0, timeout=10.0, heartbeat=None):
    """Waits (up to `timeout`) while NTR Viewer reports connection quality
    below `minimum` percent -- at 5% it can keep showing an old picture.
    Returns immediately if the quality is fine or unknown."""
    end = time.time() + timeout
    while time.time() < end:
        q = connection_quality()
        if q is None or q >= minimum:
            return True
        if heartbeat:
            heartbeat()
        time.sleep(0.25)
    return False


HEARTBEAT_STALE_MS = 10000   # frame-sharing viewer: no quality update for
                             # this long = frozen (only judged while its window
                             # isn't minimised)
_seen_viewer = False


def down_reason():
    """Why the bot shouldn't trust the picture right now, or None:
      "not responding" -- Windows reports NTR-VC's window as hung;
      "closed"         -- NTR-VC was running earlier and is gone now;
      "frozen"         -- the frame-sharing viewer stopped its heartbeat;
      "0%"             -- NTR reports 0% connection quality."""
    global _seen_viewer
    wins = _windows()
    if wins:
        _seen_viewer = True
        if any(w["hung"] or "(Not Responding)" in w["title"] for w in wins):
            return "not responding"
    if shared_source is not None:
        if not shared_source.available():
            return "closed"
        age = shared_source.heartbeat_age_ms()
        if (age is not None and age > HEARTBEAT_STALE_MS and wins
                and not any(w["minimised"] for w in wins)):
            return "frozen"
    elif _seen_viewer and not wins and sys.platform == "win32":
        return "closed"
    q = connection_quality()
    if q is not None and q <= 0.0:
        return "0%"
    return None


def is_down():
    """The picture can't be trusted right now (0% connection, or NTR-VC
    frozen / not responding / closed). May be a harmless dip."""
    return down_reason() is not None


def stream_dead(heartbeat=None):
    """True only if NTR Viewer reports 0% continuously for FREEZE_AFTER
    seconds. A shorter dip just waits it out, logs one line, and returns
    False -- no pause, nothing for the user to do."""
    global last_reason
    reason = down_reason()
    if reason is None:
        return False
    start = time.time()
    print(f"    (NTR Viewer problem: {DESCRIBE[reason]} -- waiting for it to "
          f"recover before pressing anything)", flush=True)
    while time.time() - start < FREEZE_AFTER:
        if heartbeat:
            heartbeat()
        time.sleep(0.5)
        reason = down_reason()
        if reason is None:
            print(f"    (NTR Viewer back to normal after "
                  f"{time.time() - start:.1f} s -- carrying on)", flush=True)
            return False
    last_reason = reason
    return True


DESCRIBE = {"not responding": "Windows reports it as Not Responding",
            "closed": "it has been closed",
            "frozen": "it stopped updating (heartbeat stalled)",
            "0%": "connection quality 0%"}
last_reason = None
