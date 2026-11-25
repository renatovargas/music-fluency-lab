"""Offline, velocity-sensitive keyboard sound and short chord demonstrations."""

from dataclasses import dataclass
from queue import Empty, SimpleQueue

import numpy as np


@dataclass
class Voice:
    note: int
    velocity: int
    age: int = 0
    release_at: int | None = None


class Synth:
    """Mix one stream, with independent voices for MIDI and demonstrations."""

    def __init__(self, rate: int):
        self.rate = rate
        self.commands = SimpleQueue()
        self.live: dict[int, Voice] = {}
        self.demo: dict[int, Voice] = {}

    def note_event(self, kind: str, note: int, velocity: int):
        self.commands.put(("note", (kind, note, velocity)))

    def demonstrate(self, notes: set[int]):
        self.commands.put(("demo", tuple(sorted(notes))))

    def stop_demo(self):
        self.commands.put(("stop", ()))

    def render(self, output):
        while True:
            try:
                action, args = self.commands.get_nowait()
            except Empty:
                break
            if action == "demo":
                self.demo = {note: Voice(note, 74, release_at=int(0.72 * self.rate)) for note in args}
            elif action == "stop":
                self._release_demo()
            else:
                kind, note, velocity = args
                if kind == "on":
                    self._release_demo()
                    self.live[note] = Voice(note, velocity)
                elif note in self.live and self.live[note].release_at is None:
                    self.live[note].release_at = self.live[note].age

        output.fill(0)
        offsets = np.arange(len(output), dtype=np.float32)
        for bank in (self.live, self.demo):
            for note, voice in list(bank.items()):
                if voice.age >= 6 * self.rate or (
                    voice.release_at is not None and voice.age >= voice.release_at + 0.13 * self.rate
                ):
                    del bank[note]
                    continue
                samples = offsets + voice.age
                t = samples / self.rate
                hz = 440 * 2 ** ((note - 69) / 12)
                phase = 2 * np.pi * hz * t
                tone = np.sin(phase) * np.exp(-1.5 * t)
                for harmonic, gain, decay in ((2, 0.38, 3), (3, 0.18, 5), (4, 0.09, 9)):
                    if harmonic * hz < self.rate / 2:
                        tone += gain * np.sin(harmonic * phase) * np.exp(-decay * t)
                envelope = np.minimum(t / 0.008, 1)
                if voice.release_at is not None:
                    envelope *= np.clip(1 - (samples - voice.release_at) / (0.13 * self.rate), 0, 1) ** 2
                output += tone * envelope * (0.16 * (voice.velocity / 127) ** 1.4)
                voice.age += len(output)
        np.tanh(output, out=output)

    def _release_demo(self):
        for voice in self.demo.values():
            voice.release_at = min(voice.age, voice.release_at)


class KeyboardAudio:
    def __init__(self):
        import sounddevice as sd

        rate = int(sd.query_devices(kind="output")["default_samplerate"])
        self.synth = Synth(rate)
        self.stream = sd.OutputStream(
            samplerate=rate, channels=1, dtype="float32", latency="low",
            callback=self._render,
        )
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

    def _render(self, outdata, frames, time_info, status):
        self.synth.render(outdata[:, 0])

    def close(self):
        self.stream.close()
