"""
frame_recorder.py -- grabs frames non-stop on a background thread so the
shiny flash (5 game frames, ~83 ms) can't slip by while the main loop is
busy pressing buttons. Wraps a vision.Capture or shared_frame capture and
is a drop-in replacement for it: .frame() returns the latest frame.

With the frame-sharing viewer only NEW pictures are recorded (it counts
the frames it decodes), so the gaps shiny_flash sees are the real gaps
between stream frames, and a slow stream shows up as "unsure" instead of
quietly missing a shiny. A screen grab can't tell a repeated stream frame
from a still screen, so there every grab counts: reading the screen
relies on NTR Viewer streaming smoothly (see the README).
"""

import threading
import time

import numpy as np

import gb_screen
import shiny_flash


LOCATE_MIN_BRIGHT = 100   # mean brightness (0-255) of the game picture at
                          # which a frame is trusted to show where the game
                          # sits in the capture
RELOCATE_FRAMES = 30      # a smaller game picture must be found on this many
                          # bright frames (no full-size one between) first


class RecordingCapture:
    def __init__(self, cap, keep_seconds=60.0):
        self.cap = cap
        self.recorder = shiny_flash.FlashRecorder(keep_seconds)
        self._game = None
        self._smaller = 0
        self._lock = threading.Lock()
        self._latest = None
        self._error = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _grabber(self):
        """A frame-grab function for this thread. Screen captures keep one
        mss handle open here (opening one per grab is too slow to keep up
        with the stream)."""
        region = getattr(self.cap, "region", None)
        if region is None:
            return self.cap.frame, getattr(self.cap, "frame_index", None)
        import cv2
        import mss
        sct = mss.mss()

        def grab():
            return cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)
        return grab, None

    def _native(self, frame):
        """The frame at Game Boy resolution. gb_screen.find_game() locates
        the game by its bright columns, which fails on the flash itself:
        the screen goes mostly black, and in NTR-VC's frames (the whole
        3DS top screen, the game picture in the middle) it then reads the
        whole frame as the game and the flash no longer looks like a
        photo-negative -- a missed shiny. The game sits in the same place
        in every frame, so a dark frame reuses where the last bright one
        found it.

        On the Game Boy Color the flash only blacks out the battle field:
        the text box and the Pokemon stay lit, and with the game at 1x in
        NTR-VC's frame find_game() can then lock onto a small bright patch
        of them -- which looks bright, so the flash vanished. A smaller
        picture than the known one is therefore only believed once it has
        been found on RELOCATE_FRAMES bright frames with no full-size one
        in between."""
        h, w = frame.shape[:2]
        if (w % gb_screen.GB_W == 0 and h % gb_screen.GB_H == 0
                and w // gb_screen.GB_W == h // gb_screen.GB_H):
            return gb_screen.native(frame)     # already just the game
        game = gb_screen.find_game(frame)
        native = gb_screen.to_native(frame, game)
        if game != (0, 0, w, h) and native.mean() >= LOCATE_MIN_BRIGHT:
            if self._game is None or game[2] >= self._game[2] - 4:
                self._game, self._smaller = game, 0
                return native
            self._smaller += 1
            if self._smaller >= RELOCATE_FRAMES:
                self._game, self._smaller = game, 0
                return native
        if self._game is not None and game != self._game:
            native = gb_screen.to_native(frame, self._game)
        return native

    def _run(self):
        grab, frame_index = None, None
        last_index = None
        while not self._stop:
            try:
                if grab is None:
                    grab, frame_index = self._grabber()
                frame = grab()
                now = time.time()
                with self._lock:
                    self._latest = frame
                if frame_index is not None:
                    # The index of the picture frame() just returned. Asking
                    # frame_index() separately could already report the NEXT
                    # picture, which would then be skipped as "seen".
                    index = getattr(self.cap, "last_index", None)
                    if index is None:
                        index = frame_index()
                    if index == last_index:
                        time.sleep(0.002)
                        continue
                    last_index = index
                else:
                    time.sleep(0.005)
                native = self._native(frame)
                with self._lock:
                    self.recorder.add(now, native)
            except Exception as e:      # keep recording; frame() reports it
                self._error = e
                grab = None
                time.sleep(0.1)

    def frame(self):
        end = time.time() + 5.0
        while True:
            with self._lock:
                latest = self._latest
            if latest is not None:
                return latest
            if time.time() > end:
                raise RuntimeError(f"no frames from the capture ({self._error})")
            time.sleep(0.01)

    def clear(self):
        """Forget everything recorded so far (call at each soft reset)."""
        with self._lock:
            self.recorder.clear()

    def analyse(self):
        with self._lock:
            stats = list(self.recorder.stats)
        return shiny_flash.analyse(stats)

    def close(self):
        self._stop = True
