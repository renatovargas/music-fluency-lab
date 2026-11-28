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
from mfl.exercises.base import KEY_CHORDS_NOTE, Exercise, PianoView, View, cadence_events, chord_events
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
    why = ""

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

    def intro(self):
        return self.title, self.why, self.intro_steps() + [
            f"{self.rounds} rounds. A wrong answer replays the sound; two wrong answers show it on the keyboard.",
            "H replays the sound.",
        ]

    def intro_steps(self) -> list[str]:  # pragma: no cover - interface
        return []


# What each degree does, in a few words (semitones above the tonic).
DEGREE_MEANING = {
    0: "home: where melodies come to rest",
    1: "a tense half step above home",
    2: "one step above home, wants to fall back",
    3: "the minor third: the sad colour of a minor key",
    4: "the bright middle of the home chord",
    5: "leans down onto mi",
    6: "the restless tritone",
    7: "the strong top of the home chord",
    8: "the minor sixth: leans down onto sol",
    9: "sweet and open: home of the relative minor",
    10: "the flat seventh: bluesy, rock and Latin colour",
    11: "the leading tone: pulls up to do",
}


class DegreeExercise(RoundExercise):
    """Anchored first: play home, then meet each note of today's set (hear it,
    play the highlighted key). Only then the quiz, where every round plays
    home before the mystery note and the possible answers are marked."""

    kind = "degrees"
    title = "Find the scale degree"
    why = ("Hearing where a note sits relative to home is how you find a melody by ear and work out "
           "which key a singer is in.")

    def intro_steps(self):
        names = ", ".join(solfege(o) for o in self.offsets)
        first = (f"First we meet the notes ({names}): I play each one, you play the highlighted key."
                 if self.mode == "new" else "First, find home: play do, the highlighted key.")
        return [f"I play a few chords in {self.key.name}. They only set the key (just listen): "
                f"{self.key.tonic.text} is home, do.",
                first,
                "Then the quiz: each time I play home, then a mystery note. Play the mystery note. "
                "The possible answers are marked on the keyboard.",
                "Hum it before you play if that helps. Any octave is fine."]

    @property
    def show_options(self) -> bool:
        return len(self.offsets) <= 4 or self.mode == "new"

    def place(self, offset: int) -> int:
        note = self.tonic_midi + offset
        return note - 12 if note > self.ctx.high - 2 else note

    def start(self, now):
        Exercise.start(self, now)
        self.teaching = True
        self.teach_queue = [0] + ([o for o in self.offsets if o != 0] if self.mode == "new" else [])
        self._teach_next(now, first=True)

    def _teach_next(self, now, first: bool = False):
        self.answered = False
        if not self.teach_queue:
            self.teaching = False
            self.round = 0
            self.misses = 0
            self.new_round()
            self._listen(now, with_cadence=True)
            self.say(f"Quiz time. {KEY_CHORDS_NOTE} Then home, then a mystery note: play the mystery note.",
                     "info")
            return
        self.offset = self.teach_queue.pop(0)
        self.target = self.place(self.offset)
        events, end = cadence_events(self.key) if first else ([], 0.0)
        t = end + 0.45 if first else 0.0
        if self.offset != 0:
            events.append(NoteEvent(t, self.tonic_midi, 76, 0.6))
            t += 0.8
        events.append(NoteEvent(t, self.target, 84, 1.3))
        self.ctx.demo(events, now, gap=0.4)
        if first:
            self.say(f"{KEY_CHORDS_NOTE} Then play the highlighted key: home, {self.key.tonic.text}, do.", "info")
        elif self.offset == 0:
            self.say(f"This is home: {self.key.tonic.text}, do. Play the highlighted key.", "info")
        else:
            self.say(f"Home, then {solfege(self.offset)}. Play the highlighted key.", "info")

    def can_answer(self, now) -> bool:
        return True if self.teaching else super().can_answer(now)

    def _next(self, now):
        if self.teaching:
            self._teach_next(now)
        else:
            super()._next(now)

    def hint(self, now):
        if self.teaching:
            events = [NoteEvent(0.0, self.tonic_midi, 76, 0.6), NoteEvent(0.8, self.target, 84, 1.3)]
            self.ctx.demo(events, now, gap=0.3)
        else:
            super().hint(now)

    def _teach_view(self) -> View:
        marks = {self.target: solfege(self.offset)}
        piano = PianoView(held=frozenset(self.ctx.held), target=frozenset({self.target}),
                          good_pcs=frozenset({self.target % 12}), marks=marks,
                          tonic_pcs=frozenset({self.key.tonic.pc}))
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        return View(block=self.block, title="Meet the notes of the key", big=chromatic_degree_label(self.offset),
                    big_tone="good" if self.answered else "accent",
                    caption=f"{solfege(self.offset)} · {DEGREE_MEANING[self.offset]}", key=f"Key: {self.key.name}",
                    lesson="Sing or hum it along with the keyboard. Notice how it feels against home.",
                    piano=piano, feedback=feedback, tone=tone, listening=self.listening())

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
        self.target = self.place(self.offset)
        self.wrong_offset = None

    def round_events(self, with_cadence):
        # Always re-anchor: home first (after the cadence when there is one).
        events, end = cadence_events(self.key) if with_cadence else ([], 0.0)
        start = end + 0.45 if with_cadence else 0.0
        events.append(NoteEvent(start, self.tonic_midi, 76, 0.6))
        start += 0.9
        events.append(NoteEvent(start, self.target, 84, 1.3))
        return events, start

    def _label(self, offset: int) -> str:
        return f"{chromatic_degree_label(offset)} · {solfege(offset)}"

    def answer(self, note, now):
        offset = (note - self.key.tonic.pc) % 12
        if self.teaching:
            if offset == self.offset:
                self.answered = True
                self.say(f"✓ {self._label(offset)}: {DEGREE_MEANING[offset]}. Let go for the next one.", "good")
            else:
                self.say(f"That was {solfege(offset)}. Play the highlighted key.", "warn")
            return
        if offset == self.offset:
            self.correct(now, f"✓ {self._label(offset)}: {DEGREE_MEANING[offset]}", self._resolution())
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
        if getattr(self, "teaching", False):
            return self._teach_view()
        labels = [self._label(o) for o in self.offsets]
        answer_index = self.offsets.index(self.offset) if (self.answered or self.revealed) else None
        big = chromatic_degree_label(self.offset) if (self.answered or self.revealed) else "?"
        marks = {self.place(o): solfege(o) for o in self.offsets} if self.show_options else {}
        if self.revealed:
            marks[self.target] = "★"
        piano = PianoView(held=frozenset(self.ctx.held), target=frozenset({self.target}) if self.revealed else frozenset(),
                          good_pcs=frozenset({self.target % 12}) if self.answered or self.revealed else None,
                          marks=marks, tonic_pcs=frozenset({self.key.tonic.pc}))
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        if not feedback:
            feedback = ("Listening: home, then the mystery note…" if self.listening()
                        else "Play the mystery note. Any octave works. H plays it again.")
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
    """Hear a short melody, play it back. Oriented first: the learner plays
    the scale up from home with the keys lit, so the key and its notes are
    in the hands before any test. The scale's keys stay labelled, melodies
    stay inside that octave, the first note is shown, and a wrong note
    never wipes progress: the melody replays and the learner carries on."""

    kind = "echo"
    title = "Echo the melody"
    why = "Playing back what you hear is the first step to playing songs without a chart."

    def intro_steps(self):
        tonic = self.key.tonic.text
        return [f"First, find your way around: play the {self.key.name} scale up from home ({tonic}, do), "
                "following the lit key.",
                f"Then I play a short melody: {self.length} single notes, no chords.",
                "Hum it, then play the same notes. The first note is lit, and every note you need is one of "
                "the labelled keys.",
                "A wrong note doesn't start you over: I replay the melody and you carry on where you were. "
                "Miss twice and I light the next key."]

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.length = int(item.get("length", 3))
        self.phrase: list[int] = []
        self.position = 0
        self.shift = 0
        self.tonic_midi = 60 + (self.key.tonic.pc - 60) % 12
        if self.tonic_midi > 66:
            self.tonic_midi -= 12
        offsets = self.key.scale.formula_semitones()
        self.scale = [self.tonic_midi + o for o in offsets] + [self.tonic_midi + 12]
        self.orienting = False
        self.scale_position = 0

    # ---- orientation: play the scale from home -------------------------------------
    def start(self, now):
        Exercise.start(self, now)
        self.orienting = True
        self.scale_position = 0
        events = [NoteEvent(0.4 * i, n, 78, 0.38) for i, n in enumerate(self.scale)]
        self.ctx.demo(events, now, gap=0.4)
        self.say(f"This is the {self.key.name} scale, from home ({self.key.tonic.text}, do). "
                 "Now you: play the lit key, then the next.", "info")

    def _orientation_note(self, note, now):
        expected = self.scale[self.scale_position]
        if note % 12 != expected % 12:
            self.say(f"That's {self.key.spell(note).text}. Play the lit key ({self.key.spell(expected).text}).",
                     "warn")
            return
        self.scale_position += 1
        if self.scale_position < len(self.scale):
            self.say(f"✓ {solfege(expected - self.tonic_midi)}. Next: the lit key.", "good")
            return
        self.orienting = False
        self.say("✓ That's the whole scale. Every melody uses only these labelled keys. "
                 "Let go and listen to the first melody.", "good")
        self.answered = True  # release moves on to the first round

    # ---- rounds ----------------------------------------------------------------------
    def new_round(self):
        self.phrase = make_phrase(self.key, self.length, self.ctx.rng, self.scale[0], self.scale[-1])
        self.position = 0
        self.shift = 0

    def round_events(self, with_cadence):
        # The melody only: the key was set by the scale and stays on screen.
        return [NoteEvent(0.55 * i, n, 86, 0.5) for i, n in enumerate(self.phrase)], 0.0

    def _next(self, now):
        if self.round == 0 and not self.phrase:  # orientation finished
            self.answered = False
            self.misses = 0
            self.new_round()
            self._listen(now)
            return
        super()._next(now)

    def can_answer(self, now) -> bool:
        if self.orienting:
            return True
        handle = self.ctx.demo_handle
        if handle is None or self.revealed or handle.state == "done":
            return True
        # Allow answering once the whole melody has been heard.
        end_offset = self.target_offset + 0.55 * (len(self.phrase) - 1)
        if handle.state in ("playing", "cancelled") and handle.start is not None:
            return handle.offset_reached(end_offset, now)
        return False

    def answer(self, note, now):
        if self.orienting:
            self._orientation_note(note, now)
            return
        if not self.phrase:
            return
        if self.position == 0:
            shift = note - self.phrase[0]
            self.shift = shift if shift % 12 == 0 else 0
        expected = self.phrase[self.position] + self.shift
        if note == expected:
            self.position += 1
            if self.position == len(self.phrase):
                names = " ".join(solfege(n - self.tonic_midi) for n in self.phrase)
                self.correct(now, f"✓ {names}")
            else:
                self.say(f"✓ {solfege(expected - self.shift - self.tonic_midi)}. Next note…", "good")
        else:
            which = "first note" if self.position == 0 else f"note {self.position + 1}"
            self.wrong(now, f"Not that one for the {which}. Your earlier notes still count.")

    def hint(self, now):
        if self.orienting or self.done:
            return
        super().hint(now)

    def _listen(self, now, with_cadence=False):
        super()._listen(now, with_cadence=False)

    # ---- view ------------------------------------------------------------------------
    def view(self, now) -> View:
        labels = {n: solfege(n - self.tonic_midi) for n in self.scale}
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        if self.orienting or not self.phrase:
            lit = self.scale[self.scale_position] if self.orienting else None
            piano = PianoView(held=frozenset(self.ctx.held), target=frozenset({lit}) if lit else frozenset(),
                              good_pcs=frozenset(n % 12 for n in self.scale), marks=labels,
                              tonic_pcs=frozenset({self.key.tonic.pc}))
            return View(block=self.block, title=f"Find your way: the {self.key.name} scale", big="do",
                        caption=f"home is {self.key.tonic.text}", key=f"Key: {self.key.name}",
                        lesson="Play up the scale from home. Hum each note as you play it.",
                        piano=piano, feedback=feedback, tone=tone, listening=self.listening())
        lit: set[int] = set()
        if self.revealed and self.position < len(self.phrase):
            lit = {self.phrase[self.position] + self.shift}  # just the next note
        elif self.position == 0 and not self.answered:
            lit = {self.phrase[0]}  # where to start
        if self.answered:
            labels = {**labels, **{n + self.shift: str(i + 1) for i, n in enumerate(self.phrase)}}
        piano = PianoView(held=frozenset(self.ctx.held), target=frozenset(lit), marks=labels,
                          tonic_pcs=frozenset({self.key.tonic.pc}))
        progress_dots = "● " * self.position + "○ " * (len(self.phrase) - self.position)
        if not feedback:
            feedback = "Listening to the melody…" if self.listening() else "Play it back, starting on the lit key."
        return View(block=self.block, title=self.title, big=progress_dots.strip() or "♪",
                    big_tone="good" if self.answered else "accent",
                    caption=f"{len(self.phrase)} notes · starts on {solfege(self.phrase[0] - self.tonic_midi)}",
                    key=f"Key: {self.key.name}",
                    lesson=f"Only the labelled keys of {self.key.name} are used. Hum the melody, then play it. "
                           "H plays it again.",
                    piano=piano, feedback=feedback, tone=tone, progress=f"{self.round + 1}/{self.rounds}",
                    listening=self.listening())


def make_phrase(key: Key, length: int, rng, low: int = 55, high: int = 76) -> list[int]:
    """An original, singable phrase: mostly steps, a few thirds, ending on
    a stable chord tone (do, mi or sol)."""
    scale_pcs = set(key.scale.pcs)
    notes = [n for n in range(low, high + 1) if n % 12 in scale_pcs]
    stable = {key.tonic.pc, key.scale.pcs[2], key.scale.pcs[4]}
    centre = [i for i, n in enumerate(notes) if n % 12 in stable and 59 <= n <= 72 and 0 < i < len(notes) - 1] \
        or [len(notes) // 2]
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
    why = ("Most songs use a few chords. Recognising I, IV, V and vi by ear lets you accompany a song "
           "you have never seen written down.")

    def intro_steps(self):
        return [f"I play a few chords in {self.key.name} that only set the key (just listen), then one "
                "single chord: that's the one to find.",
                "Play that chord back: any inversion.",
                "Listen for the bass note first, then major or minor."]

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
            feedback = (f"Listening… {KEY_CHORDS_NOTE.split('. ')[0]}; the last chord is the one to find."
                        if self.listening() else "Play the last chord you heard. Any inversion.")
        return View(block=self.block, title=self.title, big=big, big_tone="good" if self.answered else "accent",
                    caption=caption, key=f"Key: {self.key.name}",
                    lesson="Listen to the bass and the colour: major or minor? Home, away, or tense? "
                           "H: show the numeral, then the keys.",
                    piano=piano, choices=[f"{r} {self.key.chord(r).symbol}" if shown else r for r in self.vocabulary],
                    feedback=feedback, tone=tone, progress=f"{self.round + 1}/{self.rounds}",
                    listening=self.listening())
