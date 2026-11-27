"""Ear-to-hand training: hear something in a key, find it on the keyboard.

Each round establishes the key with a short cadence, plays the target and
waits for the learner's answer on the keyboard. Wrong answers replay the
target. Two misses reveal it so the learner still plays it correctly
before moving on. Hearing the resolution afterwards anchors the sound.
"""

from __future__ import annotations

from mfl import srs
from mfl.audio.engine import NoteEvent
from mfl.curriculum import CHORD_EAR_LEVELS, DEGREE_LEVELS
from mfl.exercises.base import Exercise, PianoView, View, cadence_events, chord_events
from mfl.theory import Key, comfortable_voicing, identify
from mfl.theory.scales import chromatic_degree_label, solfege


def grade_rounds(first_try: int, rounds: int, hints: int) -> tuple[int, float]:
    accuracy = first_try / max(1, rounds)
    if accuracy >= 0.85 and hints == 0:
        return srs.EASY, accuracy
    if accuracy >= 0.65:
        return srs.GOOD, accuracy
    if accuracy >= 0.4:
        return srs.HARD, accuracy
    return srs.AGAIN, accuracy


class RoundExercise(Exercise):
    """Shared flow: listen → answer → (replay | reveal) → next round."""

    block = "Ear"
    title = ""

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.key = Key.parse(item["key"])
        self.rounds = int(item.get("rounds", 5))
        self.round = 0
        self.first_try = 0
        self.misses = 0
        self.revealed = False
        self.target_offset = 0.0
        self.waiting_replay = False
        self.answered = False
        self.blocked = bool(ctx.held)
        self.results: list[bool] = []
        self.prefix: list[NoteEvent] | None = None  # resolution of the previous answer

    # Subclasses build the round's sound; return (events, offset of the target).
    def round_events(self, with_cadence: bool) -> tuple[list[NoteEvent], float]:  # pragma: no cover
        raise NotImplementedError

    def new_round(self):  # pragma: no cover
        raise NotImplementedError

    def start(self, now):
        super().start(now)
        self.new_round()
        self._listen(now, with_cadence=True)

    def _listen(self, now, with_cadence=False):
        events, self.target_offset = self.round_events(with_cadence)
        if self.prefix:
            shift = max(e.time + e.duration for e in self.prefix) + 0.5
            events = self.prefix + [NoteEvent(e.time + shift, e.note, e.velocity, e.duration, e.instrument)
                                    for e in events]
            self.target_offset += shift
            self.prefix = None
        self.ctx.demo(events, now, gap=0.4)
        self.waiting_replay = False

    def can_answer(self, now) -> bool:
        handle = self.ctx.demo_handle
        if handle is None or self.revealed:
            return True
        if handle.state in ("done",):
            return True
        if handle.state == "playing":
            return handle.offset_reached(self.target_offset, now)
        if handle.state == "cancelled":
            return handle.start is not None and handle.offset_reached(self.target_offset, now)
        return False

    def note_on(self, note, velocity, now):
        if self.blocked or self.done or self.answered:
            return
        if not self.can_answer(now):
            # The learner interrupted before hearing the target: replay it.
            self.waiting_replay = True
            self.say("Listen to the end, then answer.", "warn")
            return
        self.answer(note, now)

    def released(self, now):
        if self.blocked:
            self.blocked = False
            return
        if self.waiting_replay and not self.done:
            self._listen(now, with_cadence=self.misses == 0 and self.round == 0)
            return
        if self.answered and not self.done:
            self._next(now)

    def correct(self, now, message: str, resolution: list[NoteEvent] | None = None):
        self.answered = True
        clean = self.misses == 0 and not self.revealed
        self.results.append(clean)
        if clean:
            self.first_try += 1
        self.say(message, "good")
        self.prefix = resolution or None

    def wrong(self, now, message: str):
        self.misses += 1
        if self.misses >= 2 and not self.revealed:
            self.revealed = True
            self.say(message + " Here it is. Play it to continue.", "bad")
        else:
            self.say(message + " Listen again.", "warn")
            self.waiting_replay = True

    def _next(self, now):
        self.answered = False
        self.round += 1
        self.misses = 0
        self.revealed = False
        if self.round >= self.rounds:
            if self.prefix:
                self.ctx.demo(self.prefix, now, gap=0.3)
                self.prefix = None
            grade, accuracy = grade_rounds(self.first_try, self.rounds, self.hints)
            self.finish(now, grade, accuracy, f"{self.first_try}/{self.rounds} found on the first try",
                        {"key": self.key.ascii, "results": self.results})
            return
        self.new_round()
        self._listen(now, with_cadence=self.round % 3 == 0)

    def hint(self, now):
        if self.done:
            return
        self.hints += 1
        self._listen(now, with_cadence=True)

    def listening(self) -> bool:
        handle = self.ctx.demo_handle
        return bool(handle and handle.state == "playing")


class DegreeExercise(RoundExercise):
    kind = "degrees"
    title = "Find the scale degree"

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        level = item.get("level", "135")
        _, mode, self.offsets = DEGREE_LEVELS[level]
        if mode == "minor" and self.key.mode != "minor":
            self.key = self.key.relative
        self.tonic_midi = 60 + (self.key.tonic.pc - 60) % 12
        if self.tonic_midi > 66:
            self.tonic_midi -= 12
        self.target = self.tonic_midi
        self.offset = 0
        self.last_offset: int | None = None
        self.wrong_offset: int | None = None

    def new_round(self):
        choices = [o for o in self.offsets if o != self.last_offset] or list(self.offsets)
        self.offset = self.ctx.rng.choice(choices)
        self.last_offset = self.offset
        self.target = self.tonic_midi + self.offset
        self.wrong_offset = None
        if self.target > self.ctx.high - 2:
            self.target -= 12

    def round_events(self, with_cadence):
        events, end = cadence_events(self.key) if with_cadence else ([], 0.0)
        start = end + 0.45 if with_cadence else 0.0
        events.append(NoteEvent(start, self.target, 84, 1.3))
        return events, start

    def _label(self, offset: int) -> str:
        return f"{chromatic_degree_label(offset)} · {solfege(offset)}"

    def answer(self, note, now):
        offset = (note - self.key.tonic.pc) % 12
        if offset == self.offset:
            self.correct(now, f"✓ {self._label(offset)}", self._resolution())
        else:
            self.wrong_offset = offset
            self.wrong(now, f"That was {self._label(offset)}.")

    def _resolution(self) -> list[NoteEvent]:
        """Walk from the target to the nearest tonic through the scale."""
        scale = {(self.key.tonic.pc + o) % 12 for o in self.key.scale.formula_semitones()}
        goal = self.target + (12 - self.offset) if self.offset >= 7 else self.target - self.offset
        path, note = [self.target], self.target
        while note != goal and len(path) < 8:
            note += 1 if note < goal else -1
            if note % 12 in scale:
                path.append(note)
        if len(path) == 1:
            return [NoteEvent(0.0, self.target, 72, 0.9)]
        return [NoteEvent(0.25 * i, n, 72, 0.28 if i < len(path) - 1 else 0.9) for i, n in enumerate(path)]

    def view(self, now) -> View:
        labels = [self._label(o) for o in self.offsets]
        answer_index = self.offsets.index(self.offset) if (self.answered or self.revealed) else None
        big = chromatic_degree_label(self.offset) if (self.answered or self.revealed) else "?"
        marks = {self.target: "★"} if self.revealed else {}
        piano = PianoView(held=frozenset(self.ctx.held), target=frozenset({self.target}) if self.revealed else frozenset(),
                          good_pcs=frozenset({self.target % 12}) if self.answered or self.revealed else None,
                          marks=marks, tonic_pcs=frozenset({self.key.tonic.pc}))
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        if not feedback:
            feedback = "Listening…" if self.listening() else "Play the note you heard. Any octave works."
        return View(block=self.block, title=self.title, big=big, big_tone="good" if self.answered else "accent",
                    caption=solfege(self.offset) if self.answered else "which degree?",
                    lesson="The cadence sets home (do). Hear how the note relates to it, then find it. "
                           "Tonic keys are marked ▪.",
                    key=f"Key: {self.key.name}", piano=piano,
                    ladder=(labels, answer_index,
                            self.offsets.index(self.wrong_offset) if self.wrong_offset in self.offsets else None),
                    feedback=feedback, tone=tone, progress=f"{self.round + 1}/{self.rounds}",
                    listening=self.listening())


class EchoExercise(RoundExercise):
    kind = "echo"
    title = "Echo the phrase"

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.length = int(item.get("length", 3))
        self.phrase: list[int] = []
        self.position = 0
        self.shift = 0

    def new_round(self):
        self.phrase = make_phrase(self.key, self.length, self.ctx.rng, max(self.ctx.low, 55), min(self.ctx.high, 76))
        self.position = 0

    def round_events(self, with_cadence):
        events: list[NoteEvent] = []
        start = 0.0
        if with_cadence:
            chords = [self.key.chord(r) for r in (("I", "V", "I") if self.key.mode == "major" else ("i", "V", "i"))]
            t = 0.0
            for c in chords:
                events += chord_events(comfortable_voicing(c, 48, 67, 57), t, 0.5, 62)
                t += 0.55
            start = t + 0.5
        for i, n in enumerate(self.phrase):
            events.append(NoteEvent(start + 0.5 * i, n, 86, 0.46))
        return events, start

    def can_answer(self, now) -> bool:
        handle = self.ctx.demo_handle
        if handle is None or self.revealed or handle.state == "done":
            return True
        # Allow answering once the whole phrase has been heard.
        end_offset = self.target_offset + 0.5 * (len(self.phrase) - 1)
        if handle.state in ("playing", "cancelled") and handle.start is not None:
            return handle.offset_reached(end_offset, now)
        return False

    def answer(self, note, now):
        if self.position == 0:
            shift = note - self.phrase[0]
            self.shift = shift if shift % 12 == 0 else 0
        expected = self.phrase[self.position] + self.shift
        if note == expected:
            self.position += 1
            if self.position == len(self.phrase):
                names = " ".join(self.key.spell(n).text for n in self.phrase)
                self.correct(now, f"✓ {names}")
            else:
                self.say("♪ " + "● " * self.position + "○ " * (len(self.phrase) - self.position), "info")
        else:
            which = "first note" if self.position == 0 else f"note {self.position + 1}"
            self.position = 0
            self.wrong(now, f"Not quite: the {which} was different.")

    def view(self, now) -> View:
        shown = self.revealed or self.answered
        marks = {n + self.shift: str(i + 1) for i, n in enumerate(self.phrase)} if shown else {}
        piano = PianoView(held=frozenset(self.ctx.held),
                          target=frozenset(n + self.shift for n in self.phrase) if self.revealed else frozenset(),
                          marks=marks, tonic_pcs=frozenset({self.key.tonic.pc}))
        progress_dots = "● " * self.position + "○ " * (len(self.phrase) - self.position)
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        if not feedback:
            feedback = "Listening…" if self.listening() else "Play it back."
        return View(block=self.block, title=self.title, big=progress_dots.strip() or "♪",
                    big_tone="good" if self.answered else "accent",
                    caption=f"{len(self.phrase)} notes", key=f"Key: {self.key.name}",
                    lesson="Sing it back in your head first, then play it. Start on any octave.",
                    piano=piano, feedback=feedback, tone=tone, progress=f"{self.round + 1}/{self.rounds}",
                    listening=self.listening())


def make_phrase(key: Key, length: int, rng, low: int = 55, high: int = 76) -> list[int]:
    """An original, singable phrase: mostly steps, a few thirds, ending on
    a stable chord tone (do, mi or sol)."""
    scale_pcs = set(key.scale.pcs)
    notes = [n for n in range(low, high + 1) if n % 12 in scale_pcs]
    stable = {key.tonic.pc, key.scale.pcs[2], key.scale.pcs[4]}
    centre = [i for i, n in enumerate(notes) if n % 12 in stable and 59 <= n <= 72] or [len(notes) // 2]
    index = rng.choice(centre)
    phrase = [notes[index]]
    direction = rng.choice((-1, 1))
    while len(phrase) < length:
        roll = rng.random()
        step = 1 if roll < 0.68 else 2 if roll < 0.92 else 3
        if rng.random() < 0.3:
            direction = -direction
        candidate = index + direction * step
        if not 0 <= candidate < len(notes):
            direction = -direction
            candidate = index + direction * step
        index = max(0, min(len(notes) - 1, candidate))
        if notes[index] == phrase[-1]:
            continue
        phrase.append(notes[index])
    # Resolve the last note to the nearest stable tone.
    if phrase[-1] % 12 not in stable:
        options = [n for n in notes if n % 12 in stable and n != phrase[-2]]
        phrase[-1] = min(options, key=lambda n: (abs(n - phrase[-2]), n))
    return phrase


class ChordEarExercise(RoundExercise):
    kind = "chordear"
    title = "Which chord?"

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        _, self.vocabulary = CHORD_EAR_LEVELS[item.get("level", "I-IV-V")]
        if self.key.mode != "major":
            self.key = self.key.relative
        self.roman = "I"
        self.target = self.key.chord("I")
        self.voicing = comfortable_voicing(self.target, self.ctx.low, self.ctx.high)
        self.last: str | None = None
        self.attempt: set[int] = set()
        self.hint_level = 0

    def new_round(self):
        choices = [r for r in self.vocabulary if r != self.last]
        self.roman = self.ctx.rng.choice(choices)
        self.last = self.roman
        self.target = self.key.chord(self.roman)
        self.voicing = comfortable_voicing(self.target, self.ctx.low, self.ctx.high)
        self.attempt = set()
        self.hint_level = 0

    def round_events(self, with_cadence):
        events, end = cadence_events(self.key) if with_cadence else ([], 0.0)
        start = end + 0.45 if with_cadence else 0.0
        events += chord_events(self.voicing, start, 1.5, 80)
        events.append(NoteEvent(start, 36 + (self.target.bass_pc - 36) % 12 + (12 if self.target.bass_pc < 4 else 0),
                                72, 1.5))
        return events, start

    def answer(self, note, now):
        self.attempt.add(note)
        if self.target.matches(self.ctx.held, require_bass=False):
            self.correct(now, f"✓ {self.roman} · {self.target.symbol}")

    def released(self, now):
        if not self.blocked and not self.answered and len(self.attempt) >= 3 and not self.done:
            played = identify(self.attempt)
            if played:
                analysis = self.key.analyze(played[0]) or played[0].symbol
                self.wrong(now, f"You played {analysis} ({played[0].symbol}).")
            else:
                self.wrong(now, "That wasn't one of the chords.")
        self.attempt = set()
        super().released(now)

    def hint(self, now):
        if self.done or self.answered:
            return
        self.hints += 1
        self.hint_level += 1
        if self.hint_level >= 2:
            self.revealed = True
        self._listen(now, with_cadence=False)

    def view(self, now) -> View:
        shown = self.answered or self.revealed
        big = self.roman if (shown or self.hint_level >= 1) else "?"
        caption = self.target.symbol if shown else ("which chord?" if self.hint_level == 0 else "find it")
        target = frozenset(self.voicing) if self.revealed else frozenset()
        piano = PianoView(held=frozenset(self.ctx.held), target=target,
                          good_pcs=self.target.pcs if shown else None, tonic_pcs=frozenset({self.key.tonic.pc}))
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        if not feedback:
            feedback = "Listening…" if self.listening() else "Play the chord you heard. Any inversion."
        return View(block=self.block, title=self.title, big=big, big_tone="good" if self.answered else "accent",
                    caption=caption, key=f"Key: {self.key.name}",
                    lesson="Listen to the bass and the colour: major or minor? Home, away, or tense? "
                           "H: show the numeral, then the keys.",
                    piano=piano, choices=[f"{r} {self.key.chord(r).symbol}" if shown else r for r in self.vocabulary],
                    feedback=feedback, tone=tone, progress=f"{self.round + 1}/{self.rounds}",
                    listening=self.listening())
