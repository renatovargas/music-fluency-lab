"""Audio output. ``open_audio`` returns a device-backed engine or None."""

from __future__ import annotations

import sys
import time

from mfl.audio.engine import Engine, NoteEvent
from mfl.audio.instruments import PLAYABLE, build_instruments

INSTRUMENT_NAMES = {key: inst.name for key, inst in build_instruments().items() if key in PLAYABLE}

__all__ = ["AudioOut", "Engine", "INSTRUMENT_NAMES", "NoteEvent", "NullAudio", "PLAYABLE", "open_audio"]


class NullAudio:
    """Silent stand-in with the same control surface as AudioOut."""

    available = False
    name = "silent"
    underflows = 0

    def __init__(self):
        self.keys_instrument = "piano"
        self.volume = 0.85

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
        self.volume = max(0.0, min(1.5, volume))

    @property
    def peak(self):
        return 0.0

    def close(self):
        pass


class AudioOut:
    """The engine attached to the default output device via PortAudio."""

    available = True

    def __init__(self, instrument: str = "piano", volume: float = 0.85):
        import sounddevice as sd

        # Let the audio callback take the GIL promptly while the UI renders.
        sys.setswitchinterval(0.001)
        device = sd.query_devices(kind="output")
        rate = int(device["default_samplerate"])
        self.channels = 2 if device["max_output_channels"] >= 2 else 1
        self.name = device["name"]
        self.engine = Engine(rate, instrument=instrument, volume=volume)
        self.underflows = 0
        self._latency = 0.02
        self.stream = sd.OutputStream(
            samplerate=rate, channels=self.channels, dtype="float32", blocksize=self.engine.block,
            latency="low", callback=self._callback,
        )
        try:
            self._latency = float(self.stream.latency)
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

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


def open_audio(instrument: str = "piano", volume: float = 0.85):
    """Open the default output, raising on failure so callers can report it."""
    return AudioOut(instrument, volume)
