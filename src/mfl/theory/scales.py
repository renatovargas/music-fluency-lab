"""Scales and modes, written as degree formulas relative to the major scale."""

from __future__ import annotations

from dataclasses import dataclass

from mfl.theory.pitch import Note, degree

# name: (formula, description)
SCALES: dict[str, tuple[str, str]] = {
    "major": ("1 2 3 4 5 6 7", "Ionian. The reference for every degree and Roman numeral."),
    "natural minor": ("1 2 b3 4 5 b6 b7", "Aeolian. The relative minor of the major scale."),
    "harmonic minor": ("1 2 b3 4 5 b6 7", "Raised 7th gives minor keys a major V chord."),
    "melodic minor": ("1 2 b3 4 5 6 7", "Jazz melodic minor, the same ascending and descending."),
    "dorian": ("1 2 b3 4 5 6 b7", "Minor with a bright 6th. Heard in funk, rock and Latin vamps."),
    "phrygian": ("1 b2 b3 4 5 b6 b7", "Minor with a dark ♭2."),
    "lydian": ("1 2 3 #4 5 6 7", "Major with a floating ♯4."),
    "mixolydian": ("1 2 3 4 5 6 b7", "Major with ♭7. The sound of I–♭VII–IV rock."),
    "locrian": ("1 b2 b3 4 b5 b6 b7", "Diminished tonic. Mostly theoretical."),
    "major pentatonic": ("1 2 3 5 6", "Five notes, no half steps. Safe for melodies and fills."),
    "minor pentatonic": ("1 b3 4 5 b7", "The rock and blues soloing scale."),
    "blues": ("1 b3 4 b5 5 b7", "Minor pentatonic plus the ♭5 blue note."),
    "major blues": ("1 2 b3 3 5 6", "Major pentatonic plus ♭3. Gospel and country fills."),
    "phrygian dominant": ("1 b2 3 4 5 b6 b7", "5th mode of harmonic minor. Flamenco and the Andalusian cadence."),
    "whole tone": ("1 2 3 #4 #5 b7", "Symmetric whole steps. Augmented, dreamy."),
    "diminished half-whole": ("1 b2 #2 3 #4 5 6 b7", "Symmetric scale over dominant ♭9 chords."),
    "diminished whole-half": ("1 2 b3 4 b5 #5 6 7", "Symmetric scale over diminished 7th chords."),
    "bebop dominant": ("1 2 3 4 5 6 b7 7", "Mixolydian with a chromatic passing tone."),
    "hungarian minor": ("1 2 b3 #4 5 b6 7", "Harmonic minor with ♯4."),
}

MODES = ("major", "dorian", "phrygian", "lydian", "mixolydian", "natural minor", "locrian")


@dataclass(frozen=True)
class Scale:
    tonic: Note
    name: str = "major"

    @property
    def formula(self) -> tuple[str, ...]:
        return tuple(SCALES[self.name][0].split())

    @property
    def notes(self) -> tuple[Note, ...]:
        return tuple(self.tonic.transpose(degree(d)) for d in self.formula)

    def formula_semitones(self) -> tuple[int, ...]:
        return tuple(degree(d).semitones % 12 for d in self.formula)

    @property
    def pcs(self) -> tuple[int, ...]:
        return tuple(n.pc for n in self.notes)

    def midi_notes(self, low: int, high: int) -> list[int]:
        wanted = set(self.pcs)
        return [n for n in range(low, high + 1) if n % 12 in wanted]

    def degree_of(self, midi: int) -> int | None:
        """1-based scale degree of a MIDI note, or None if outside the scale."""
        try:
            return self.pcs.index(midi % 12) + 1
        except ValueError:
            return None

    def __str__(self) -> str:
        return f"{self.tonic} {self.name}"


def chromatic_degree_label(semitones: int) -> str:
    """Label a pitch relative to a tonic, e.g. 3 → ``♭3``, 6 → ``♯4``."""
    return ("1", "♭2", "2", "♭3", "3", "4", "♯4", "5", "♭6", "6", "♭7", "7")[semitones % 12]


def solfege(semitones: int) -> str:
    """Movable-do syllable with chromatic alterations (do, di/ra, re…)."""
    return ("do", "ra", "re", "me", "mi", "fa", "fi", "sol", "le", "la", "te", "ti")[semitones % 12]
