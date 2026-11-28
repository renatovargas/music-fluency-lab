"""Audio output. ``open_audio`` returns a device-backed engine or None."""

from __future__ import annotations

import sys
import time

from mfl.audio.engine import Engine, NoteEvent
from mfl.audio.instruments import PLAYABLE, build_instruments

DEFAULT_LATENCY = 0.045  # seconds of output buffer; raise it if you hear dropouts
MIN_LATENCY = 0.03  # below this a Python callback cannot keep up while the screen redraws
MAX_LATENCY = 0.3

INSTRUMENT_NAMES = {key: inst.name for key, inst in build_instruments().items() if key in PLAYABLE}

__all__ = ["DEFAULT_LATENCY", "MAX_LATENCY", "MIN_LATENCY", "AudioOut", "Engine", "INSTRUMENT_NAMES", "NoteEvent", "NullAudio", "PLAYABLE", "open_audio"]


class NullAudio:
    """Silent stand-in with the same control surface as AudioOut."""

    available = False
    name = "silent"
    underflows = 0

    def __init__(self):
        self.keys_instrument = "piano"
        self.volume = 1.0

    def note_on(self, note, velocity, source="live", instrument="keys"):
        pass

    def note_off(self, note, source="live"):
        pass

    def pedal(self, down):
        pass

    def play(self, events, tag="demo", source=None):
        pass

    def stop(self, tag):
        pass

    def set_instrument(self, key):
        self.keys_instrument = key

    def set_volume(self, volume):
        self.volume = max(0.0, min(2.0, volume))

    @property
    def peak(self):
        return 0.0

    def close(self):
        pass


class AudioOut:
    """The engine attached to the default output device via PortAudio."""

    available = True

    def __init__(self, instrument: str = "piano", volume: float = 1.0, latency: float = DEFAULT_LATENCY):
        import sounddevice as sd

        # Let the audio callback take the GIL promptly while the UI renders.
        sys.setswitchinterval(0.001)
        device = sd.query_devices(kind="output")
        rate = int(device["default_samplerate"])
        self.channels = 2 if device["max_output_channels"] >= 2 else 1
        self.name = device["name"]
        self.engine = Engine(rate, instrument=instrument, volume=volume)
        self.underflows = 0
        self.rate = rate
        self.requested_latency = max(MIN_LATENCY, min(MAX_LATENCY, latency))
        self._latency = self.requested_latency
        self.stream = self._open_stream(self.requested_latency)

    def _open_stream(self, latency: float):
        import sounddevice as sd

        # v0.5 asked for 256-frame callbacks at PortAudio's "low" latency: a
        # ~6 ms deadline that a Python callback misses whenever the UI holds
        # the interpreter, heard as crackles. Let the host pick the callback
        # size (blocksize 0) and keep a larger safety buffer.
        stream = sd.OutputStream(
            samplerate=self.rate, channels=self.channels, dtype="float32", blocksize=0,
            latency=latency, callback=self._callback,
        )
        try:
            self._latency = float(stream.latency)
            stream.start()
        except Exception:
            stream.close()
            raise
        return stream

    def reopen(self, latency: float) -> float:
        """Restart the output with a different buffer size (the engine and
        everything it is playing carry on)."""
        latency = max(MIN_LATENCY, min(MAX_LATENCY, latency))
        old = self.stream
        try:
            old.stop()
        finally:
            old.close()
        self.requested_latency = latency
        self.stream = self._open_stream(latency)
        return latency

    def _callback(self, outdata, frames, time_info, status):
        now = time.perf_counter()
        if status.output_underflow:
            self.underflows += 1
        ahead = time_info.outputBufferDacTime - time_info.currentTime
        if not 0.0 <= ahead < 0.5:
            ahead = self._latency
        try:
            block = self.engine.render(frames, now + ahead)
        except Exception:  # never let the audio thread die
            outdata.fill(0)
            return
        if self.channels == 2:
            outdata[:] = block
        else:
            outdata[:, 0] = block.mean(axis=1)

    # Delegate the control surface to the engine.
    def note_on(self, note, velocity, source="live", instrument="keys"):
        self.engine.note_on(note, velocity, source, instrument)

    def note_off(self, note, source="live"):
        self.engine.note_off(note, source)

    def pedal(self, down):
        self.engine.pedal(down)

    def play(self, events, tag="demo", source=None):
        self.engine.play(events, tag, source)

    def stop(self, tag):
        self.engine.stop(tag)

    def set_instrument(self, key):
        self.engine.set_instrument(key)

    def set_volume(self, volume):
        self.engine.set_volume(volume)

    @property
    def keys_instrument(self):
        return self.engine.keys_instrument

    @property
    def volume(self):
        return self.engine.volume

    @property
    def peak(self):
        return self.engine.peak

    def close(self):
        self.engine.close()
        try:
            self.stream.stop()
        finally:
            self.stream.close()


def open_audio(instrument: str = "piano", volume: float = 1.0, latency: float = DEFAULT_LATENCY):
    """Open the default output, raising on failure so callers can report it."""
    return AudioOut(instrument, volume, latency)
