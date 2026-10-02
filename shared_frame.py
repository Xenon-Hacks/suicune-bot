"""
shared_frame.py -- reads the 3DS top screen straight from the frame-sharing
build of NTRViewer-HR (frame_share.c), so NTR Viewer can be minimised,
covered or moved anywhere while the bot runs.

It's a drop-in replacement for vision.Capture: .frame() returns an upright
BGR picture. Frames are scaled x4 (400x240 -> 1600x960, about the size of
the NTR Viewer window the bot used to read), so everything that measures
the picture behaves as before. Calibrate once with:  py calibrate.py --shared

Shared memory layout: see frame_share.h in the viewer source.
"""

import mmap
import os
import struct
import sys
import time

import cv2
import numpy as np

NAME_WINDOWS = "Local\\NTRViewerHR_TopScreen"
PATH_POSIX = "/dev/shm/ntrviewer_hr_top_screen"
HEADER = struct.Struct("<8s8IQiIQ")          # 64 bytes
HEADER_SIZE = 64
MAX_PIXELS = 240 * 800
TOTAL_SIZE = HEADER_SIZE + MAX_PIXELS * 4
MAGIC = b"NTRFRAME"
SCALE = 4                     # 400x240 -> 1600x960
QUALITY_STALE_MS = 5000       # an older quality reading counts as "unknown"


def _now_ms():
    """The same system-wide clock the viewer stamps its data with."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_uint64
        return int(ctypes.windll.kernel32.GetTickCount64())
    return int(time.monotonic() * 1000)


class SharedFrameCapture:
    def __init__(self, rotation=1):
        """rotation: quarter turns (numpy.rot90) to make the 3DS's sideways
        framebuffer upright -- 1 per the viewer's renderer; check with
        test_shared_frame.py."""
        self.rotation = rotation
        self.mm = None
        self.last_index = 0
        self._blank = np.zeros((240 * SCALE, 400 * SCALE, 3), np.uint8)
        self._last = None

    # ------------------------------------------------------------ plumbing
    def _open(self):
        if self.mm is not None:
            return True
        try:
            if sys.platform == "win32":
                # Opens the viewer's mapping (or creates an empty one it will
                # then share, if the viewer isn't running yet).
                self.mm = mmap.mmap(-1, TOTAL_SIZE, tagname=NAME_WINDOWS)
            else:
                if not os.path.exists(PATH_POSIX):
                    return False
                with open(PATH_POSIX, "rb") as fh:
                    self.mm = mmap.mmap(fh.fileno(), TOTAL_SIZE, access=mmap.ACCESS_READ)
        except (OSError, ValueError):
            self.mm = None
        return self.mm is not None

    def _header(self):
        return HEADER.unpack_from(self.mm, 0)

    def available(self):
        """True once the frame-sharing viewer is running and publishing."""
        return self._open() and self._header()[0] == MAGIC

    def _read_raw(self):
        """(header fields, pixel bytes) of the newest complete frame, or
        None. Uses the viewer's sequence lock: never returns a frame that
        was being overwritten while it was copied."""
        if not self.available():
            return None
        for _ in range(100):
            seq1 = struct.unpack_from("<I", self.mm, 16)[0]
            if seq1 & 1:                      # the viewer is mid-write
                time.sleep(0.0005)
                continue
            fields = self._header()
            width, height = fields[5], fields[6]
            n = width * height * 4
            if n == 0 or n > MAX_PIXELS * 4:
                return None                   # nothing published yet
            data = bytes(self.mm[HEADER_SIZE:HEADER_SIZE + n])
            if struct.unpack_from("<I", self.mm, 16)[0] == seq1:
                return fields, data
        return None

    # ------------------------------------------------------------ public
    def frame(self):
        """Upright BGR picture of the top screen (1600x960). Black until
        the viewer has published a first frame."""
        raw = self._read_raw()
        if raw is None:
            return self._last if self._last is not None else self._blank
        fields, data = raw
        width, height, index = fields[5], fields[6], fields[4]
        if index == self.last_index and self._last is not None:
            return self._last
        pixels = np.frombuffer(data, np.uint8).reshape(height, width, 4)
        # The viewer decodes to R, G, B, A (TJPF_RGBA in its const.h);
        # OpenCV wants B, G, R.
        upright = np.rot90(pixels, self.rotation)[:, :, 2::-1]         # RGBA -> BGR
        big = cv2.resize(np.ascontiguousarray(upright),
                         (upright.shape[1] * SCALE, upright.shape[0] * SCALE),
                         interpolation=cv2.INTER_NEAREST)
        self.last_index, self._last = index, big
        return big

    def frame_index(self):
        """Counter that goes up by one for every frame the viewer decodes."""
        if not self.available():
            return None
        return self._header()[4]

    def heartbeat_age_ms(self):
        """How long ago the viewer last updated its connection quality
        (about once a second while it runs), or None if never."""
        if not self.available():
            return None
        stamp = self._header()[12]
        return None if stamp == 0 else _now_ms() - stamp

    def quality(self):
        """NTR Viewer's connection quality in percent, or None if unknown
        (viewer not running, or no recent reading)."""
        if not self.available():
            return None
        fields = self._header()
        q10, stamp = fields[10], fields[12]
        if q10 < 0 or stamp == 0 or _now_ms() - stamp > QUALITY_STALE_MS:
            return None
        return q10 / 10.0


def wait_until_available(cap, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cap.available() and cap.frame_index():
            return True
        time.sleep(0.2)
    return False
