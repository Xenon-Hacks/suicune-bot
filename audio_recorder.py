"""
audio_recorder.py -- records what the PC is playing (Windows WASAPI
loopback of the default speakers) on a background thread, so the bot can
listen for the shiny sound (shine_sound.py) in NTR-VC's game audio.
The fallback for an NTR-VC older than 2.2.0: newer ones share their audio
directly (shared_audio.py), which the bot prefers.

NTR-VC must be streaming the 3DS's audio (its Debug window: DSP audio
capture). The recording is what Windows plays AFTER each app's volume,
so NTR-VC at 0 or muted in the volume mixer records as silence. To hunt
without hearing the game, send NTR-VC to an output nobody listens to
(Settings > Sound > Volume mixer > NTR-VC > Output device, e.g.
"Speakers (Steam Streaming Speakers)"), keep its volume up, and run the
bot with --audio-device "Steam Streaming". Other programs' sound on the
same output is recorded too.
"""

import collections
import threading
import time
import warnings

import numpy as np

SR = 48000
BLOCK = 480                 # 10 ms


class AudioRecorder:
    sr = SR

    def __init__(self, device=None, keep_seconds=30.0):
        """device: part of an output device's name (default: the default
        speakers)."""
        import soundcard
        warnings.filterwarnings("ignore", module="soundcard")
        if device:
            found = [s for s in soundcard.all_speakers()
                     if device.lower() in s.name.lower()]
            if not found:
                names = ", ".join(s.name for s in soundcard.all_speakers())
                raise RuntimeError(f"no output device matching {device!r} "
                                   f"(there are: {names})")
            speaker = found[0]
        else:
            speaker = soundcard.default_speaker()
        self.device = speaker.name
        self._mic = soundcard.get_microphone(id=str(speaker.name),
                                             include_loopback=True)
        self._blocks = collections.deque(maxlen=int(keep_seconds * SR / BLOCK))
        self._lock = threading.Lock()
        self._stop = False
        self.error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            with self._mic.recorder(samplerate=SR, channels=2, blocksize=BLOCK) as rec:
                while not self._stop:
                    data = rec.record(numframes=BLOCK)
                    now = time.time()
                    with self._lock:
                        self._blocks.append((now, data.mean(axis=1).astype(np.float32)))
        except Exception as e:          # analyse() reports it
            self.error = e

    def since(self, t0):
        """Mono audio recorded from time t0 (time.time()) until now."""
        with self._lock:
            blocks = [b for t, b in self._blocks if t >= t0]
        return np.concatenate(blocks) if blocks else np.zeros(0, np.float32)

    def close(self):
        self._stop = True
