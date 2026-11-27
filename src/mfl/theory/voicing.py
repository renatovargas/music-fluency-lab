"""Voicings and voice leading for one hand on small keyboards.

Pianists accompanying singers rarely jump between root-position chords.
They keep common tones and move the other voices by step. These helpers
find such economical voicings inside a playable register.
"""

from __future__ import annotations

from itertools import permutations

from mfl.theory.chords import Chord

# A comfortable right-hand window that fits a 25-key controller at its
# default octave (C3–C5) and the middle of any larger keyboard.
DEFAULT_LOW, DEFAULT_HIGH, DEFAULT_CENTER = 53, 77, 65


def chord_tones(chord: Chord, max_notes: int = 4) -> list[int]:
    """Pitch classes for a one-hand voicing, most essential first.

    Large extended chords drop the fifth, then the root, as keyboardists do.
    """
    tones = [n.pc for n in chord.notes]
    if len(tones) > max_notes and chord.quality.has_perfect_fifth:
        tones.pop(chord.quality.formula.index("5"))
    if len(tones) > max_notes:
        tones = tones[1:]  # rootless: the bass or band supplies the root
    return tones[:max_notes] if len(tones) > max_notes else tones


def close_voicings(chord: Chord, low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH,
                   max_notes: int = 4) -> list[tuple[int, ...]]:
    """Every inversion in close position, in every octave between low and high."""
    tones = chord_tones(chord, max_notes)
    results = set()
    for rotation in range(len(tones)):
        order = tones[rotation:] + tones[:rotation]
        for start in range(low - 12, high + 1):
            if start % 12 != order[0]:
                continue
            voicing = [start]
            for pc in order[1:]:
                step = (pc - voicing[-1]) % 12 or 12
                voicing.append(voicing[-1] + step)
            if voicing[0] >= low and voicing[-1] <= high:
                results.add(tuple(voicing))
    return sorted(results)


def voice_leading_distance(previous, current) -> int | None:
    """Minimum total semitone movement between two voicings.

    Equal sizes use the best one-to-one assignment. Different sizes count each
    voice's distance to its nearest partner. This is a voicing-distance proxy,
    not a measure of finger movement.
    """
    a, b = sorted(previous), sorted(current)
    if not a or not b:
        return None
    if len(a) == len(b) and len(a) <= 6:
        return min(sum(abs(x - y) for x, y in zip(a, p)) for p in permutations(b))
    forward = sum(min(abs(x - y) for y in b) for x in a)
    backward = sum(min(abs(x - y) for x in a) for y in b)
    return (forward + backward) // 2


def comfortable_voicing(chord: Chord, low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH,
                        center: int = DEFAULT_CENTER) -> tuple[int, ...]:
    """A good first voicing: near the centre, root position preferred."""
    options = close_voicings(chord, low, high)
    if not options:
        options = close_voicings(chord, low - 12, high + 12)

    def cost(voicing):
        mean = sum(voicing) / len(voicing)
        root_position = voicing[0] % 12 == chord.root.pc
        return abs(mean - center) + (0 if root_position else 3)

    return min(options, key=cost)


def voice_lead(previous, chord: Chord, low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH,
               center: int = DEFAULT_CENTER) -> tuple[int, ...]:
    """The voicing of ``chord`` nearest to the previous voicing."""
    if not previous:
        return comfortable_voicing(chord, low, high, center)
    options = close_voicings(chord, low, high) or [comfortable_voicing(chord, low, high, center)]

    def cost(voicing):
        drift = abs(sum(voicing) / len(voicing) - center) * 0.15  # avoid creeping off the keyboard
        return voice_leading_distance(previous, voicing) + drift

    return min(options, key=cost)


def lead_progression(chords: list[Chord], low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH,
                     start=None) -> list[tuple[int, ...]]:
    """Voice-led voicings for a whole progression."""
    voicings: list[tuple[int, ...]] = []
    previous = start
    for item in chords:
        previous = voice_lead(previous, item, low, high)
        voicings.append(previous)
    return voicings


def bass_note(chord: Chord, low: int = 36, high: int = 50) -> int:
    """The chord's bass (root or slash bass) in a low register."""
    pc = chord.bass_pc
    candidates = [n for n in range(low, high + 1) if n % 12 == pc]
    return candidates[0] if candidates else low + (pc - low) % 12


def movement_report(previous, current) -> str:
    """Describe a chord change the way a teacher would."""
    if not previous or not current:
        return ""
    common = len({n for n in previous} & {n for n in current})
    distance = voice_leading_distance(previous, current) or 0
    parts = []
    if common:
        parts.append(f"{common} common tone{'s' if common > 1 else ''} held")
    parts.append(f"{distance} semitone{'s' if distance != 1 else ''} of movement")
    return ", ".join(parts)
