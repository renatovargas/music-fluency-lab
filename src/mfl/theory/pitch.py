"""Spelled notes, intervals and MIDI helpers.

Notes are spelled (letter + accidental) so that a key or chord can be written
the way musicians read it: F♯ in D major, B♭ in F major, never "A#" for a
B-flat chord. MIDI numbers stay plain integers throughout the code base.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

LETTERS = "CDEFGAB"
NATURAL_PC = (0, 2, 4, 5, 7, 9, 11)
SHARP, FLAT = "♯", "♭"
SOLFEGE = ("do", "re", "mi", "fa", "sol", "la", "ti")


@dataclass(frozen=True)
class Interval:
    """An interval with both letter distance (steps) and size (semitones)."""

    steps: int  # 0 = unison, 2 = third, 7 = octave
    semitones: int

    QUALITY_NAMES = {"P": "perfect", "M": "major", "m": "minor", "A": "augmented", "d": "diminished"}
    NUMBER_NAMES = {
        1: "unison", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh",
        8: "octave", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth",
    }

    @property
    def number(self) -> int:
        return self.steps + 1

    @property
    def quality(self) -> str:
        simple_steps = self.steps % 7
        reference = NATURAL_PC[simple_steps] + 12 * (self.steps // 7)
        diff = self.semitones - reference
        if simple_steps in (0, 3, 4):
            return {0: "P", 1: "A", -1: "d", 2: "AA", -2: "dd"}.get(diff, "?")
        return {0: "M", -1: "m", 1: "A", -2: "d", 2: "AA", -3: "dd"}.get(diff, "?")

    @property
    def short(self) -> str:
        return f"{self.quality}{self.number}"

    @property
    def name(self) -> str:
        quality = "".join(self.QUALITY_NAMES.get(q, q) for q in self.quality[:1])
        if len(self.quality) == 2:
            quality = "doubly " + quality
        number = self.NUMBER_NAMES.get(self.number, f"{self.number}th")
        return "octave" if self.short == "P8" else "unison" if self.short == "P1" else f"{quality} {number}"

    @classmethod
    def parse(cls, text: str) -> Interval:
        """Parse ``M3``, ``P5``, ``m7`` or degree style ``b3``, ``#11``, ``bb7``."""
        match = re.fullmatch(r"([PMmAd])(\d+)", text)
        if match:
            quality, number = match.group(1), int(match.group(2))
            steps = number - 1
            reference = NATURAL_PC[steps % 7] + 12 * (steps // 7)
            perfect = steps % 7 in (0, 3, 4)
            offsets = {"P": 0, "A": 1, "d": -1} if perfect else {"M": 0, "m": -1, "A": 1, "d": -2}
            if quality not in offsets:
                raise ValueError(f"Invalid interval {text!r}")
            return cls(steps, reference + offsets[quality])
        return degree(text)

    def __add__(self, other: Interval) -> Interval:
        return Interval(self.steps + other.steps, self.semitones + other.semitones)

    def __str__(self) -> str:
        return self.short


def degree(text: str) -> Interval:
    """A scale degree relative to the major scale: ``1``, ``b3``, ``#4``, ``bb7``, ``13``."""
    match = re.fullmatch(r"([b#♭♯]*)(\d+)", text.strip())
    if not match or int(match.group(2)) < 1:
        raise ValueError(f"Invalid degree {text!r}")
    accidentals, number = match.groups()
    steps = int(number) - 1
    semitones = NATURAL_PC[steps % 7] + 12 * (steps // 7)
    semitones += sum(1 if a in "#♯" else -1 for a in accidentals)
    return Interval(steps, semitones)


SEMITONE_NAMES = (
    "unison", "minor second", "major second", "minor third", "major third", "perfect fourth",
    "tritone", "perfect fifth", "minor sixth", "major sixth", "minor seventh", "major seventh", "octave",
)


def interval_name(semitones: int) -> str:
    """Common name for an interval size, used in ear-training feedback."""
    semitones = abs(semitones)
    if semitones <= 12:
        return SEMITONE_NAMES[semitones]
    return f"{SEMITONE_NAMES[semitones % 12]} + {semitones // 12} octave(s)"


@dataclass(frozen=True)
class Note:
    """A spelled pitch class such as C, F♯ or B♭."""

    letter: int  # index into LETTERS
    alter: int = 0  # +1 sharp, -1 flat

    @property
    def pc(self) -> int:
        return (NATURAL_PC[self.letter] + self.alter) % 12

    @property
    def letter_name(self) -> str:
        return LETTERS[self.letter]

    @property
    def text(self) -> str:
        """Unicode spelling for display: ``F♯``, ``B♭``, ``E𝄫`` as ``E♭♭``."""
        return self.letter_name + (SHARP * self.alter if self.alter > 0 else FLAT * -self.alter)

    @property
    def ascii(self) -> str:
        return self.letter_name + ("#" * self.alter if self.alter > 0 else "b" * -self.alter)

    def __str__(self) -> str:
        return self.text

    @classmethod
    def parse(cls, text: str) -> Note:
        match = re.fullmatch(r"([A-Ga-g])([#♯b♭]*)", text.strip())
        if not match:
            raise ValueError(f"Invalid note name {text!r}")
        letter = LETTERS.index(match.group(1).upper())
        alter = sum(1 if a in "#♯" else -1 for a in match.group(2))
        return cls(letter, alter)

    def transpose(self, interval: Interval, down: bool = False) -> Note:
        sign = -1 if down else 1
        letter = (self.letter + sign * interval.steps) % 7
        target = (self.pc + sign * interval.semitones) % 12
        alter = (target - NATURAL_PC[letter] + 6) % 12 - 6
        return Note(letter, alter)

    def interval_to(self, other: Note) -> Interval:
        steps = (other.letter - self.letter) % 7
        semitones = (other.pc - self.pc) % 12
        return Interval(steps, semitones)

    def midi(self, octave: int) -> int:
        """MIDI number in scientific pitch octave (C4 = 60). B♯3 is 60, C♭4 is 59."""
        return 12 * (octave + 1) + NATURAL_PC[self.letter] + self.alter

    def enharmonic(self) -> Note:
        """The simpler alternative spelling, e.g. A♯ → B♭, E♯ → F."""
        if self.alter == 0:
            return self
        candidates = [Note(letter, (self.pc - NATURAL_PC[letter] + 6) % 12 - 6) for letter in range(7)]
        candidates = [n for n in candidates if n != self and abs(n.alter) <= 1]
        return min(candidates, key=lambda n: abs(n.alter)) if candidates else self


# Default spellings when no key context exists. Flats for common flat keys,
# F♯ rather than G♭, as pop/rock lead sheets usually write them.
DEFAULT_SPELLING = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
SHARP_SPELLING = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_SPELLING = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def spell_pc(pc: int, prefer: str = "default") -> Note:
    table = {"sharps": SHARP_SPELLING, "flats": FLAT_SPELLING}.get(prefer, DEFAULT_SPELLING)
    return Note.parse(table[pc % 12])


def note_name(midi: int, prefer: str = "default", unicode: bool = False) -> str:
    """Name a MIDI note: 60 → ``C4``. ASCII by default for compatibility."""
    note = spell_pc(midi, prefer)
    return f"{note.text if unicode else note.ascii}{midi // 12 - 1}"


def parse_midi(text: str) -> int:
    """Parse ``C4``, ``F#3`` or ``Bb2`` into a MIDI number."""
    match = re.fullmatch(r"([A-Ga-g][#♯b♭]*)(-?\d+)", text.strip())
    if not match:
        raise ValueError(f"Invalid pitch {text!r}")
    return Note.parse(match.group(1)).midi(int(match.group(2)))


def midi_hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def is_black(midi: int) -> bool:
    return midi % 12 in (1, 3, 6, 8, 10)


def pcs(notes) -> frozenset[int]:
    return frozenset(n % 12 for n in notes)
