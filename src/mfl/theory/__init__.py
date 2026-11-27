"""Music theory for MFL: notes, intervals, scales, chords, keys, voice leading,
progressions and rhythm. Pure Python, no dependencies."""

from mfl.theory.chords import (
    BY_SUFFIX, QUALITIES, Chord, Quality, chord, identify, matches_chord, name_notes, parse_chord,
)
from mfl.theory.keys import CIRCLE_OF_FIFTHS, Key, estimate_key, harmonic_function, roman_chord
from mfl.theory.pitch import (
    Interval, Note, degree, interval_name, is_black, midi_hz, note_name, parse_midi, pcs, spell_pc,
)
from mfl.theory.progressions import PROGRESSIONS, Progression
from mfl.theory.rhythm import COMP_PATTERNS, GROOVES, CompPattern
from mfl.theory.scales import SCALES, Scale, chromatic_degree_label, solfege
from mfl.theory.voicing import (
    bass_note, close_voicings, comfortable_voicing, lead_progression, movement_report, voice_lead,
    voice_leading_distance,
)

__all__ = [
    "BY_SUFFIX", "CIRCLE_OF_FIFTHS", "COMP_PATTERNS", "GROOVES", "PROGRESSIONS", "QUALITIES", "SCALES",
    "Chord", "CompPattern", "Interval", "Key", "Note", "Progression", "Quality", "Scale",
    "bass_note", "chord", "chromatic_degree_label", "close_voicings", "comfortable_voicing", "degree",
    "estimate_key", "harmonic_function", "identify", "interval_name", "is_black", "lead_progression",
    "matches_chord", "midi_hz", "movement_report", "name_notes", "note_name", "parse_chord", "parse_midi",
    "pcs", "roman_chord", "solfege", "spell_pc", "voice_lead", "voice_leading_distance",
]
