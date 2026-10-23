"""
shared_audio.py -- listens to the 3DS game audio straight from NTR-VC's
shared memory (audio_share.c in the viewer source), so the PC's volume,
mute and output device don't matter: NTR-VC can be muted, at 0, or on
any output, and other programs' sound is never mixed in.

It's a drop-in replacement for audio_recorder.AudioRecorder: a background
thread collects the audio, .since(t0) returns it as mono float32 at
.sr Hz (32728, the 3DS's rate). Needs an NTR-VC build with audio sharing
(2.2.0 or later) and NTR-VC's audio on (its Debug window: Audio (NTR-HR+)).

Shared memory layout: see audio_share.h in the viewer source.
"""

import collections
import mmap
import os
import struct
import sys
import threading
import time

import numpy as np

NAME_WINDOWS = "Local\\NTRViewerHR_Audio"
PATH_POSIX = "/dev/shm/ntrviewer_hr_audio"
HEADER = struct.Struct("<8s6I2Q")       # magic .. write_time_ms (48 bytes)
HEADER_SIZE = 64
SR = 32728
CHANNELS = 2
RING_FRAMES = 262144                    # ~8 s
TOTAL_SIZE = HEADER_SIZE + RING_FRAMES * CHANNELS * 2
MAGIC = b"NTRAUDIO"
WRITE_COUNT_AT = 32
POLL = 0.01                             # s


def open_mapping(name=NAME_WINDOWS, path=PATH_POSIX):
    """The viewer's audio mapping, or None. On Windows this creates an
    empty one if the viewer isn't running yet; the viewer then shares it."""
    try:
        if sys.platform == "win32":
            return mmap.mmap(-1, TOTAL_SIZE, tagname=name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            return mmap.mmap(fh.fileno(), TOTAL_SIZE, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return None


def _header_ok(mm):
    magic, _ver, hsize, sr, ch, ring, _sid, _w, _t = HEADER.unpack_from(mm, 0)
    return (magic == MAGIC and hsize == HEADER_SIZE and sr == SR
            and ch == CHANNELS and ring == RING_FRAMES)


def available(timeout=0.0, name=NAME_WINDOWS, path=PATH_POSIX):
    """True if a viewer with audio sharing is running (waits up to
    `timeout` s for it)."""
    end = time.time() + timeout
    while True:
        mm = open_mapping(name, path)
        if mm is not None:
            try:
                if _header_ok(mm):
                    return True
            finally:
                mm.close()
        if time.time() >= end:
            return False
        time.sleep(0.1)


class SharedAudioRecorder:
    sr = SR

    def __init__(self, keep_seconds=30.0, name=NAME_WINDOWS, path=PATH_POSIX):
        self.device = "NTR-VC shared memory (volume and output device don't matter)"
        self._name, self._path = name, path
        self._mm = None
        self._read = None             # write_count read up to
        self._blocks = collections.deque(maxlen=int(keep_seconds / POLL) + 16)
        self._lock = threading.Lock()
        self._stop = False
        self.error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _write_count(self):
        return struct.unpack_from("<Q", self._mm, WRITE_COUNT_AT)[0]

    def _copy(self, start, end):
        """Interleaved int16 sample frames start..end (end - start <= ring)."""
        a, b = start % RING_FRAMES, end % RING_FRAMES
        bpf = CHANNELS * 2
        if end - start == 0:
            return np.zeros((0, CHANNELS), np.int16)
        if a < b:
            raw = self._mm[HEADER_SIZE + a * bpf:HEADER_SIZE + b * bpf]
        else:                          # wraps around the ring's end
            raw = (self._mm[HEADER_SIZE + a * bpf:HEADER_SIZE + RING_FRAMES * bpf]
                   + self._mm[HEADER_SIZE:HEADER_SIZE + b * bpf])
        return np.frombuffer(raw, np.int16).reshape(-1, CHANNELS)

    def poll(self):
        """Collects the audio the viewer wrote since the last poll."""
        if self._mm is None:
            self._mm = open_mapping(self._name, self._path)
            if self._mm is None:
                return
        if not _header_ok(self._mm):
            self._read = None          # viewer not (yet / any more) running
            return
        w1 = self._write_count()
        if self._read is None or w1 < self._read:
            self._read = w1            # first look, or the viewer restarted
            return
        start = max(self._read, w1 - RING_FRAMES)
        frames = self._copy(start, w1)
        # Frames the viewer overwrote while they were copied are invalid.
        w2 = self._write_count()
        drop = max(0, (w2 - RING_FRAMES) - start)
        frames = frames[drop:]
        self._read = w1
        if len(frames):
            mono = frames.astype(np.float32).mean(axis=1) / 32768.0
            with self._lock:
                self._blocks.append((time.time(), mono))

    def _run(self):
        try:
            while not self._stop:
                self.poll()
                time.sleep(POLL)
        except Exception as e:          # sound_check reports it
            self.error = e

    def since(self, t0):
        """Mono audio received from time t0 (time.time()) until now."""
        with self._lock:
            blocks = [b for t, b in self._blocks if t >= t0]
        return np.concatenate(blocks) if blocks else np.zeros(0, np.float32)

    def close(self):
        self._stop = True
