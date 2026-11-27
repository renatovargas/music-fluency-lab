"""Exercise protocol, shared view models and the demonstration gate.

Exercises are UI-agnostic state machines driven by MIDI events and a clock.
They describe what to show as a ``View`` and request sound through the
``Context``, which owns audio timing rules:

* demonstrations never start while keys are held, and wait for a clear
  gap after the learner's last release (no double sound),
* the learner's first new note cancels a pending or playing demonstration,
* backing tracks (band, metronome) are never cancelled by playing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

from mfl.audio.engine import NoteEvent

DEMO_GAP = 0.75  # seconds of silence after release before a demonstration


@dataclass
class PianoView:
    held: frozenset = frozenset()
    target: frozenset = frozenset()
    good_pcs: frozenset | None = None  # held notes in these pitch classes are green; None = neutral
    roots: frozenset = frozenset()
    marks: dict = field(default_factory=dict)  # midi → short label
    tonic_pcs: frozenset = frozenset()
    low: int | None = None
    high: int | None = None


@dataclass
class ChartView:
    cells: list[str]
    current: int | None = None
    statuses: dict = field(default_factory=dict)  # index → "good" | "miss" | "hint"
    caption: str = ""
    per_row: int = 8


@dataclass
class LaneView:
    beats_per_bar: int
    window_start: float  # beat at the left edge
    window_beats: float
    now: float  # current beat (may be negative during count-in)
    expected: list[tuple[float, str]] = field(default_factory=list)  # (beat, status)
    strays: list[float] = field(default_factory=list)
    labels: list[tuple[float, str]] = field(default_factory=list)  # chord labels at beats
    banner: str = ""


@dataclass
class View:
    block: str = ""
    title: str = ""
    big: str | None = None
    big_tone: str = "accent"
    caption: str = ""
    lesson: str = ""
    key: str = ""
    piano: PianoView | None = None
    chart: ChartView | None = None
    lane: LaneView | None = None
    ladder: tuple[list[str], int | None, int | None] | None = None  # labels, answer index, wrong index
    choices: list[str] = field(default_factory=list)
    feedback: str = ""
    tone: str = "info"  # info, good, warn, bad
    progress: str = ""
    listening: bool = False


@dataclass
class Result:
    skill: str
    kind: str
    grade: int
    score: float
    seconds: float
    hints: int
    summary: str
    details: dict = field(default_factory=dict)
    graded: bool = True


class Demo:
    """A requested demonstration with relative-time events."""

    def __init__(self, events: list[NoteEvent], gap: float, requested: float, interruptible: bool = True):
        self.events = events
        self.gap = gap
        self.requested = requested
        self.interruptible = interruptible
        self.state = "pending"  # pending → playing → done | cancelled
        self.start: float | None = None
        self.length = max((e.time + e.duration for e in events), default=0.0)

    @property
    def end(self) -> float | None:
        return None if self.start is None else self.start + self.length

    def offset_reached(self, offset: float, now: float) -> bool:
        return self.start is not None and now >= self.start + offset

    def active(self) -> bool:
        return self.state in ("pending", "playing")


class Context:
    """Services an exercise may use: audio, held keys, randomness, settings."""

    def __init__(self, audio, store=None, rng: random.Random | None = None, low: int = 53, high: int = 77):
        self.audio = audio
        self.store = store
        self.rng = rng or random.Random()
        self.low, self.high = low, high
        self.held: set[int] = set()
        self.last_release = -math.inf
        self.last_note_on = -math.inf
        self.demo_handle: Demo | None = None
        self.timing_offset = float(store.setting("timing_offset", 0.0)) if store is not None else 0.0

    # ---- demonstrations --------------------------------------------------------------
    def demo(self, events: list[NoteEvent], now: float, gap: float = DEMO_GAP,
             interruptible: bool = True) -> Demo:
        self.cancel_demo()
        self.demo_handle = Demo(sorted(events, key=lambda e: e.time), gap, now, interruptible)
        self.update(now)
        return self.demo_handle

    def cancel_demo(self):
        handle = self.demo_handle
        if handle is not None and handle.active():
            handle.state = "cancelled"
            self.audio.stop("demo")
        self.demo_handle = None

    def update(self, now: float):
        handle = self.demo_handle
        if handle is None:
            return
        if handle.state == "pending":
            quiet_since = max(self.last_release, handle.requested - handle.gap)
            if not self.held and now - quiet_since >= handle.gap:
                handle.start = now + 0.05
                handle.state = "playing"
                self.audio.play(
                    [NoteEvent(handle.start + e.time, e.note, e.velocity, e.duration, e.instrument)
                     for e in handle.events],
                    tag="demo",
                )
        elif handle.state == "playing" and handle.end is not None and now >= handle.end:
            handle.state = "done"

    def learner_note_on(self, now: float):
        handle = self.demo_handle
        if handle is not None and handle.active() and handle.interruptible:
            handle.state = "cancelled"
            self.audio.stop("demo")

    # ---- backing band -------------------------------------------------------------------
    def backing(self, events: list[NoteEvent], tag: str = "backing"):
        self.audio.play(events, tag=tag, source="backing")

    def stop_backing(self, tag: str = "backing"):
        self.audio.stop(tag)

    def save_timing_offset(self, value: float):
        self.timing_offset = max(-0.12, min(0.12, value))
        if self.store is not None:
            self.store.set_setting("timing_offset", round(self.timing_offset, 4))


class Exercise:
    kind = ""
    block = ""
    timed = False  # timed exercises need fast screen refresh

    def __init__(self, item: dict, ctx: Context):
        self.item = item
        self.ctx = ctx
        self.skill_id = item.get("skill", "")
        self.mode = item.get("mode", "review")
        self.done = False
        self.result: Result | None = None
        self.hints = 0
        self.started = 0.0
        self.feedback = ""
        self.tone = "info"

    # Lifecycle hooks (override as needed).
    def start(self, now: float):
        self.started = now

    def note_on(self, note: int, velocity: int, now: float):
        pass

    def note_off(self, note: int, now: float):
        pass

    def released(self, now: float):
        pass

    def tick(self, now: float):
        pass

    def hint(self, now: float):
        pass

    def stop(self):
        """Called when the exercise ends or is skipped. Silence anything ongoing."""
        self.ctx.cancel_demo()

    def view(self, now: float) -> View:  # pragma: no cover - interface
        raise NotImplementedError

    # Helpers.
    def say(self, text: str, tone: str = "info"):
        self.feedback, self.tone = text, tone

    def finish(self, now: float, grade: int, score: float, summary: str, details: dict | None = None,
               graded: bool = True):
        if self.done:
            return
        self.done = True
        graded = graded and self.item.get("graded", True)
        self.result = Result(self.skill_id, self.kind, grade, round(score, 3), round(now - self.started, 2),
                             self.hints, summary, details or {}, graded)


def chord_events(notes, start: float, duration: float, velocity: int = 78, roll: float = 0.0) -> list[NoteEvent]:
    return [NoteEvent(start + i * roll, n, velocity, duration - i * roll) for i, n in enumerate(sorted(notes))]


def cadence_events(key, start: float = 0.0, step: float = 0.55, low: int = 53, high: int = 72) -> tuple[list, float]:
    """I–IV–V–I in a key, voice-led, returning events and the end offset."""
    from mfl.theory import lead_progression

    romans = ("I", "IV", "V", "I") if key.mode == "major" else ("i", "iv", "V", "i")
    chords = [key.chord(r) for r in romans]
    voicings = lead_progression(chords, low, high)
    events = []
    for i, (c, v) in enumerate(zip(chords, voicings)):
        t = start + i * step
        events += chord_events(v, t, step * 0.95 if i < 3 else step * 1.6, 70)
        bass = c.root.pc + 36
        events.append(NoteEvent(t, bass if bass >= 40 else bass + 12, 64, step * 0.95 if i < 3 else step * 1.6))
    return events, start + step * 3 + step * 1.6
