"""Simple, explicit MIDI pitch-class and chord utilities."""
from collections import Counter

NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
CHORDS = {
    "C": (0, 4, 7), "Am": (9, 0, 4), "F": (5, 9, 0),
    "G": (7, 11, 2), "Dm": (2, 5, 9), "Em": (4, 7, 11),
    "D": (2, 6, 9), "Bm": (11, 2, 6), "A": (9, 1, 4),
    "E": (4, 8, 11),
}

def note_name(midi_note: int) -> str:
    return f"{NAMES[midi_note % 12]}{midi_note // 12 - 1}"

def matches_chord(notes: set[int], name: str) -> bool:
    """Exactly three distinct sounding notes, any inversion or octave."""
    return len(notes) == 3 and Counter(n % 12 for n in notes) == Counter(CHORDS[name])

def voice_leading_distance(previous: set[int], current: set[int]) -> int | None:
    """Minimum total MIDI semitone movement between two 3-note voicings.

    This is a voicing-distance proxy, not a measure of actual finger movement.
    """
    if len(previous) != 3 or len(current) != 3:
        return None
    from itertools import permutations
    a = sorted(previous)
    return min(sum(abs(x-y) for x, y in zip(a, p)) for p in permutations(current))
