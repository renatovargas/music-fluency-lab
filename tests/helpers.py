"""Shared fakes: a recording audio backend and a manual clock."""

from __future__ import annotations


class FakeAudio:
    available = True
    name = "fake"
    underflows = 0
    peak = 0.0

    def __init__(self):
        self.played: list[tuple[str, list]] = []
        self.stopped: list[str] = []
        self.live: list[tuple] = []
        self.keys_instrument = "piano"
        self.volume = 0.85

    def note_on(self, note, velocity, source="live", instrument="keys"):
        self.live.append(("on", note, velocity, source))

    def note_off(self, note, source="live"):
        self.live.append(("off", note, 0, source))

    def pedal(self, down):
        self.live.append(("pedal", int(down), 0, "live"))

    def play(self, events, tag="demo", source=None):
        self.played.append((tag, list(events)))

    def stop(self, tag):
        self.stopped.append(tag)

    def set_instrument(self, key):
        self.keys_instrument = key

    def set_volume(self, volume):
        self.volume = volume

    def close(self):
        pass

    def demos(self):
        return [events for tag, events in self.played if tag == "demo"]


class Clock:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t


class Rig:
    """Drive one exercise the way the session does, with fake time and audio."""

    def __init__(self, item: dict, store=None, seed: int = 1, start: float = 100.0):
        import random

        from mfl.exercises import Context, build

        self.audio = FakeAudio()
        self.clock = Clock(start)
        self.ctx = Context(self.audio, store, random.Random(seed))
        self.ex = build(item, self.ctx)
        self.ex.start(self.clock())
        self.ctx.update(self.clock())

    @property
    def now(self):
        return self.clock()

    def on(self, *notes, velocity=90):
        for note in notes:
            self.ctx.held.add(note)
            self.ctx.last_note_on = self.now
            self.ctx.learner_note_on(self.now)
            self.ex.note_on(note, velocity, self.now)

    def off(self, *notes):
        for note in notes or tuple(self.ctx.held):
            self.ctx.held.discard(note)
            self.ex.note_off(note, self.now)
            if not self.ctx.held:
                self.ctx.last_release = self.now
                self.ex.released(self.now)

    def tap(self, *notes, hold: float = 0.2):
        self.on(*notes)
        self.wait(hold)
        self.off(*notes)

    def wait(self, seconds: float, step: float = 0.02):
        end = self.now + seconds
        while self.now < end - 1e-9:
            self.clock.advance(min(step, end - self.now))
            self.ctx.update(self.now)
            self.ex.tick(self.now)
