"""shared_audio.py against a fake viewer that writes NTR-VC's audio ring
exactly as audio_share.c does: the audio comes through whole and in order,
across the ring's end, after the reader falls behind by more than the ring,
and after the viewer restarts. No 3DS or viewer needed."""

import mmap
import os
import struct
import sys
import uuid

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shared_audio as sa  # noqa: E402
import shine_sound  # noqa: E402


class FakeViewer:
    def __init__(self):
        tag = uuid.uuid4().hex
        self.name = "Local\\NTRAudioTest_" + tag
        self.path = "/dev/shm/ntrviewer_hr_audio_test_" + tag
        if sys.platform == "win32":
            self.mm = mmap.mmap(-1, sa.TOTAL_SIZE, tagname=self.name)
        else:
            if not os.path.isdir("/dev/shm"):
                pytest.skip("no /dev/shm")
            with open(self.path, "w+b") as fh:
                fh.truncate(sa.TOTAL_SIZE)
                self.mm = mmap.mmap(fh.fileno(), sa.TOTAL_SIZE)
        self.start()

    def start(self):
        """What audio_share_init() does (also on a viewer restart)."""
        self.mm[0:sa.HEADER_SIZE] = bytes(sa.HEADER_SIZE)
        struct.pack_into("<6I", self.mm, 8, 1, sa.HEADER_SIZE, sa.SR,
                         sa.CHANNELS, sa.RING_FRAMES, 0)
        self.mm[0:8] = sa.MAGIC
        self.w = 0

    def write(self, stereo):
        """stereo: (n, 2) int16, written like audio_share_write()."""
        bpf = sa.CHANNELS * 2
        data = np.ascontiguousarray(stereo, np.int16)
        while len(data):
            at = self.w % sa.RING_FRAMES
            n = min(sa.RING_FRAMES - at, len(data))
            off = sa.HEADER_SIZE + at * bpf
            self.mm[off:off + n * bpf] = data[:n].tobytes()
            data = data[n:]
            self.w += n
        struct.pack_into("<Q", self.mm, sa.WRITE_COUNT_AT, self.w)

    def recorder(self):
        rec = sa.SharedAudioRecorder(name=self.name, path=self.path)
        rec.close()                    # the test polls by hand
        rec._thread.join()
        return rec

    def close(self):
        self.mm.close()
        if sys.platform != "win32" and os.path.exists(self.path):
            os.remove(self.path)


@pytest.fixture
def viewer():
    v = FakeViewer()
    yield v
    v.close()


def stereo_of(mono):
    s = np.clip(mono * 32767, -32768, 32767).astype(np.int16)
    return np.stack([s, s], axis=1)


def test_available(viewer):
    assert sa.available(name=viewer.name, path=viewer.path)
    viewer.mm[0:8] = bytes(8)
    assert not sa.available(name=viewer.name, path=viewer.path)


def test_audio_arrives_whole_across_the_ring_end(viewer):
    rec = viewer.recorder()
    rec.poll()                                   # first look: from now on
    viewer.write(np.zeros((sa.RING_FRAMES - 1000, 2), np.int16))
    rec.poll()
    rng = np.random.default_rng(1)
    sent = rng.integers(-20000, 20000, (5000, 2)).astype(np.int16)
    for chunk in np.array_split(sent, 31):       # 160-frame-ish packets
        viewer.write(chunk)
    rec.poll()
    got = rec._blocks[-1][1]
    assert np.allclose(got, sent.astype(np.float32).mean(axis=1) / 32768)


def test_shine_sound_through_shared_memory_is_found(viewer):
    rec = viewer.recorder()
    rec.poll()
    x = np.zeros(int(sa.SR * 4), np.float32)
    shine = shine_sound.synth(sa.SR) * 0.25
    i = int(sa.SR * 1.5)
    x[i:i + len(shine)] += shine
    for chunk in np.array_split(stereo_of(x), 200):
        viewer.write(chunk)
        rec.poll()
    got = rec.since(0)
    assert len(got) == len(x)
    score, at = shine_sound.best_match(got, rec.sr)
    assert score > 0.3, score
    assert abs(at - 1.5) < 0.05, at


def test_falling_behind_keeps_only_the_newest_ring(viewer):
    rec = viewer.recorder()
    rec.poll()
    viewer.write(np.full((sa.RING_FRAMES + 5000, 2), 7, np.int16))
    rec.poll()
    assert len(rec.since(0)) == sa.RING_FRAMES


def test_viewer_restart_resyncs(viewer):
    rec = viewer.recorder()
    rec.poll()
    viewer.write(np.full((10000, 2), 100, np.int16))
    rec.poll()
    viewer.start()                               # write_count back to 0
    rec.poll()
    viewer.write(np.full((3000, 2), 200, np.int16))
    rec.poll()
    last = rec._blocks[-1][1]
    assert len(last) == 3000 and np.allclose(last, 200 / 32768)
