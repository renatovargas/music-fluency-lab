"""Session policy and MIDI attempt boundaries."""

from dataclasses import dataclass
import time

from mfl.storage import Progress
from mfl.theory import matches_chord, voice_leading_distance


@dataclass(frozen=True)
class Step:
    chord: str
    name: str
    voicing: tuple[int, int, int]
    lesson: str
    recall_first: bool = False


C = Step("C", "C major", (60, 64, 67), "Start with C, then add E and G above it.")
AM = Step("Am", "A minor", (60, 64, 69), "From C major, keep C and E. Move G up to A.")
F = Step("F", "F major", (60, 65, 69), "From C–E–A, move E up one white key to F.")
G = Step("G", "G major", (59, 62, 67), "Put B at the bottom. Hear how G major leads back to C.")
SESSION = (
    C, AM, F, G,
    Step(C.chord, C.name, C.voicing, C.lesson, recall_first=True),
    Step(AM.chord, AM.name, AM.voicing, AM.lesson, recall_first=True),
    Step(G.chord, G.name, G.voicing, G.lesson, recall_first=True),
)


class SessionCoach:
    def __init__(self, progress: Progress, guided_successes: int = 2, recall_misses: int = 2):
        if min(guided_successes, recall_misses) < 1:
            raise ValueError("Practice thresholds must be positive")
        self.progress = progress
        self.guided_successes = guided_successes
        self.recall_misses = recall_misses
        self.held: set[int] = set()
        self.restart()

    @property
    def step(self) -> Step:
        return SESSION[self.index]

    @property
    def target(self) -> set[int]:
        # The first matching pitch class anchors the guide for this attempt.
        shift = self.octave_shift or 0
        return {note + shift for note in self.step.voicing}

    def restart(self):
        self.index = 0
        self.finished = False
        self.previous_voicing: set[int] | None = None
        self._begin_step()

    def _begin_step(self):
        self.phase = "recall" if self.step.recall_first else "guided"
        self.guided_count = 0
        self.misses = 0
        self.octave_shift: int | None = None
        self._reset_attempt()
        self.feedback = ""

    def _reset_attempt(self):
        self.blocked = bool(self.held)
        self.accepted = False
        self.wrong: set[int] | None = None
        self.started = time.monotonic()

    def _record(self, exercise: str, success: bool, notes: set[int]):
        distance = None
        if success and self.previous_voicing is not None:
            distance = voice_leading_distance(self.previous_voicing, notes)
        self.progress.record(exercise, self.step.chord, success, time.monotonic() - self.started, notes, distance)
        if success:
            self.previous_voicing = notes.copy()

    def _advance(self):
        if self.index == len(SESSION) - 1:
            self.finished = True
            self.progress.mark_session_complete()
        else:
            self.index += 1
            self._begin_step()

    def _guide(self, message: str):
        self.phase = "guided"
        self.guided_count = 0
        self.misses = 0
        self.octave_shift = None
        self._reset_attempt()
        self.feedback = message

    def hint(self):
        if not self.finished and not self.accepted and self.phase == "recall":
            self._guide("Here’s the voicing. Play it, then try again from memory.")

    def skip(self):
        if not self.finished and not self.accepted:
            self._record("chord_skip", False, self.held)
            self._advance()

    def note_event(self, kind: str, note: int):
        if kind == "off":
            if note in self.held:
                self.held.remove(note)
                if not self.held:
                    self._released()
            return
        if note in self.held:
            return
        self.held.add(note)
        if self.finished or self.blocked or self.accepted:
            return
        if self.phase == "guided" and self.octave_shift is None:
            for pitch in self.step.voicing:
                shift = note - pitch
                if shift % 12 == 0 and all(0 <= key + shift <= 127 for key in self.step.voicing):
                    self.octave_shift = shift
                    break
        if len(self.held) < 3:
            return
        correct = self.held == self.target if self.phase == "guided" else matches_chord(self.held, self.step.chord)
        if correct:
            self._record(f"chord_{self.phase}", True, self.held)
            self.accepted = True
            self.feedback = "✓ That’s it. Release all keys to continue."
        elif self.wrong is None:
            self.wrong = self.held.copy()
            self.feedback = "Try again. Release all keys, then play the chord."

    def _released(self):
        if self.finished:
            return
        if self.accepted:
            if self.phase == "recall":
                self._advance()
                return
            self.guided_count += 1
            if self.guided_count >= self.guided_successes:
                self.phase = "recall"
                self.feedback = "Now play it from memory."
            else:
                self.feedback = "✓ Play the same shape again."
        elif self.wrong is not None:
            self._record(f"chord_{self.phase}", False, self.wrong)
            if self.phase == "recall":
                self.misses += 1
                if self.misses >= self.recall_misses:
                    self._guide("Let’s play it with the guide, then try from memory again.")
                    return
        self.octave_shift = None
        self._reset_attempt()
