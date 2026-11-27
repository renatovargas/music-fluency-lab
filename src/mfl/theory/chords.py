"""Chord qualities, symbol parsing, spelling and identification from MIDI notes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from mfl.theory.pitch import Note, degree, pcs as pitch_classes


@dataclass(frozen=True)
class Quality:
    suffix: str  # canonical, ASCII, used in stable IDs: "", "m", "maj7", "m7b5"
    formula: tuple[str, ...]
    name: str
    aliases: tuple[str, ...] = ()
    display: str | None = None  # Unicode display suffix if different

    @property
    def intervals(self):
        return tuple(degree(d) for d in self.formula)

    @property
    def semitones(self) -> tuple[int, ...]:
        return tuple(i.semitones % 12 for i in self.intervals)

    @property
    def has_perfect_fifth(self) -> bool:
        return "5" in self.formula

    @property
    def shown(self) -> str:
        return self.display if self.display is not None else self.suffix.replace("b", "♭").replace("#", "♯")


def _q(suffix, formula, name, aliases=(), display=None):
    return Quality(suffix, tuple(formula.split()), name, tuple(aliases), display)


# Ordered roughly from common to rare. Identification prefers earlier entries.
QUALITIES: tuple[Quality, ...] = (
    _q("", "1 3 5", "major", ("M", "maj", "major")),
    _q("m", "1 b3 5", "minor", ("min", "-", "minor", "mi")),
    _q("7", "1 3 5 b7", "dominant seventh", ("dom7", "dom")),
    _q("maj7", "1 3 5 7", "major seventh", ("M7", "Δ7", "Δ", "ma7", "maj")),
    _q("m7", "1 b3 5 b7", "minor seventh", ("min7", "-7", "mi7")),
    _q("sus4", "1 4 5", "suspended fourth", ("sus",)),
    _q("sus2", "1 2 5", "suspended second"),
    _q("dim", "1 b3 b5", "diminished", ("°", "o", "mb5"), display="°"),
    _q("aug", "1 3 #5", "augmented", ("+", "#5"), display="+"),
    _q("6", "1 3 5 6", "major sixth", ("M6", "maj6")),
    _q("m6", "1 b3 5 6", "minor sixth", ("min6", "-6")),
    _q("add9", "1 3 5 9", "added ninth", ("add2", "2")),
    _q("madd9", "1 b3 5 9", "minor added ninth", ("m(add9)", "madd2", "m2")),
    _q("m7b5", "1 b3 b5 b7", "half-diminished seventh", ("ø", "ø7", "-7b5", "min7b5"), display="ø7"),
    _q("dim7", "1 b3 b5 bb7", "diminished seventh", ("°7", "o7"), display="°7"),
    _q("7sus4", "1 4 5 b7", "dominant seventh suspended fourth", ("7sus",)),
    _q("9", "1 3 5 b7 9", "dominant ninth"),
    _q("maj9", "1 3 5 7 9", "major ninth", ("M9", "Δ9")),
    _q("m9", "1 b3 5 b7 9", "minor ninth", ("min9", "-9")),
    _q("6/9", "1 3 5 6 9", "six-nine", ("69", "6add9")),
    _q("mMaj7", "1 b3 5 7", "minor-major seventh", ("m(maj7)", "mM7", "-Δ7", "mmaj7")),
    _q("aug7", "1 3 #5 b7", "augmented seventh", ("7#5", "+7", "7+5")),
    _q("maj7#5", "1 3 #5 7", "augmented major seventh", ("+maj7", "maj7+5")),
    _q("7b5", "1 3 b5 b7", "dominant seventh flat five"),
    _q("7b9", "1 3 5 b7 b9", "dominant seventh flat nine"),
    _q("7#9", "1 3 5 b7 #9", "dominant seventh sharp nine"),
    _q("9sus4", "1 4 5 b7 9", "dominant ninth suspended fourth", ("9sus",)),
    _q("7#11", "1 3 5 b7 #11", "dominant seventh sharp eleven"),
    _q("maj7#11", "1 3 5 7 #11", "major seventh sharp eleven", ("Δ#11",)),
    _q("7b13", "1 3 5 b7 b13", "dominant seventh flat thirteen"),
    _q("11", "1 3 5 b7 9 11", "dominant eleventh"),
    _q("m11", "1 b3 5 b7 9 11", "minor eleventh", ("min11", "-11")),
    _q("13", "1 3 5 b7 9 13", "dominant thirteenth"),
    _q("maj13", "1 3 5 7 9 13", "major thirteenth", ("M13", "Δ13")),
    _q("m13", "1 b3 5 b7 9 13", "minor thirteenth", ("min13", "-13")),
    _q("5", "1 5", "power chord"),
)

BY_SUFFIX = {q.suffix: q for q in QUALITIES}
_ALIASES: dict[str, Quality] = {}
for _quality in QUALITIES:
    for _name in (_quality.suffix, *_quality.aliases):
        _ALIASES.setdefault(_name, _quality)

# Root spellings without key context; minor chords favour sharps (C♯m, G♯m).
MAJOR_ROOTS = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MINOR_ROOTS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")


@dataclass(frozen=True)
class Chord:
    root: Note
    quality: Quality
    bass: Note | None = None  # slash bass, None when the root is in the bass

    @property
    def notes(self) -> tuple[Note, ...]:
        return tuple(self.root.transpose(i) for i in self.quality.intervals)

    @property
    def pcs(self) -> frozenset[int]:
        result = {n.pc for n in self.notes}
        if self.bass is not None:
            result.add(self.bass.pc)
        return frozenset(result)

    @property
    def bass_pc(self) -> int:
        return (self.bass or self.root).pc

    @property
    def symbol(self) -> str:
        """Unicode display symbol: ``F♯m7``, ``B♭``, ``C/E``, ``Bø7``."""
        text = self.root.text + self.quality.shown
        return f"{text}/{self.bass.text}" if self.bass else text

    @property
    def ascii(self) -> str:
        """Stable ASCII symbol for IDs and storage: ``F#m7``, ``Bb``, ``C/E``."""
        text = self.root.ascii + self.quality.suffix
        return f"{text}/{self.bass.ascii}" if self.bass else text

    @property
    def name(self) -> str:
        text = f"{self.root.text} {self.quality.name}"
        return f"{text} over {self.bass.text}" if self.bass else text

    @property
    def spelled(self) -> str:
        return " ".join(n.text for n in self.notes)

    def with_bass(self, bass: Note | None) -> Chord:
        return Chord(self.root, self.quality, None if bass is None or bass.pc == self.root.pc else bass)

    def transpose(self, interval, down: bool = False) -> Chord:
        bass = self.bass.transpose(interval, down) if self.bass else None
        return Chord(self.root.transpose(interval, down), self.quality, bass)

    def essential_pcs(self) -> frozenset[int]:
        """Chord tones that must sound. The perfect fifth may be left out of
        four-or-more-note chords, as pianists routinely do."""
        tones = [n.pc for n in self.notes]
        if len(tones) >= 4 and self.quality.has_perfect_fifth:
            fifth = self.root.transpose(degree("5")).pc
            tones = [pc for pc in tones if pc != fifth]
        if self.bass is not None:
            tones.append(self.bass.pc)
        return frozenset(tones)

    def matches(self, notes, *, require_bass: bool | None = None) -> bool:
        """True when held MIDI notes sound this chord in any inversion,
        octave or doubling. Slash chords require their bass at the bottom."""
        if not notes:
            return False
        held = pitch_classes(notes)
        if not (self.essential_pcs() <= held <= self.pcs):
            return False
        need_bass = self.bass is not None if require_bass is None else require_bass
        return not need_bass or min(notes) % 12 == self.bass_pc

    def __str__(self) -> str:
        return self.symbol


_SYMBOL = re.compile(r"^([A-Ga-g][#♯b♭]?)(.*?)(?:/([A-Ga-g][#♯b♭]?))?$")


@lru_cache(maxsize=512)
def parse_chord(text: str) -> Chord:
    """Parse a chord symbol: ``C``, ``F#m7``, ``Bb/D``, ``Gsus4``, ``Eø7``, ``A7b9``."""
    match = _SYMBOL.match(text.strip())
    if not match:
        raise ValueError(f"Invalid chord symbol {text!r}")
    root_text, suffix, bass_text = match.groups()
    root = Note.parse(root_text)
    quality = _ALIASES.get(suffix)
    if quality is None:
        normalized = suffix.replace("♭", "b").replace("♯", "#")
        quality = _ALIASES.get(normalized) or _ALIASES.get(normalized.replace("(", "").replace(")", ""))
    if quality is None:
        raise ValueError(f"Unknown chord quality {suffix!r} in {text!r}")
    bass = Note.parse(bass_text) if bass_text else None
    return Chord(root, quality).with_bass(bass)


def chord(root: str | Note, suffix: str = "") -> Chord:
    root_note = Note.parse(root) if isinstance(root, str) else root
    return Chord(root_note, BY_SUFFIX[suffix])


def default_root(pc: int, quality: Quality) -> Note:
    minorish = quality.formula[1:2] == ("b3",)
    return Note.parse((MINOR_ROOTS if minorish else MAJOR_ROOTS)[pc % 12])


def identify(notes, *, spell=None) -> list[Chord]:
    """Name the chord formed by held MIDI notes, best match first.

    ``spell(pc, quality)`` may supply root spellings from a key context.
    Inversions are written as slash chords (C/E). Returns [] for fewer than
    two distinct pitch classes or unrecognized sets.
    """
    if not notes:
        return []
    held = pitch_classes(notes)
    if len(held) < 2:
        return []
    bass = min(notes) % 12
    spell = spell or default_root
    found: list[tuple[tuple, Chord]] = []
    for rank, quality in enumerate(QUALITIES):
        if quality.suffix == "5" and len(held) != 2:
            continue
        for root in held:
            tones = frozenset((root + s) % 12 for s in quality.semitones)
            exact = tones == held
            no_fifth = (
                len(tones) >= 4 and quality.has_perfect_fifth and tones - {(root + 7) % 12} == held
            )
            if not (exact or no_fifth):
                continue
            root_note = spell(root, quality)
            candidate = Chord(root_note, quality)
            if bass != root:
                bass_note = next((n for n in candidate.notes if n.pc == bass), None)
                candidate = candidate.with_bass(bass_note)
            # Prefer root in bass, exact sets, common qualities, then simple symbols.
            score = (bass != root, not exact, rank, len(candidate.ascii))
            found.append((score, candidate))
    found.sort(key=lambda item: item[0])
    return [c for _, c in found]


def name_notes(notes) -> str | None:
    matches = identify(notes)
    return matches[0].symbol if matches else None


def matches_chord(notes, symbol: str | Chord) -> bool:
    target = parse_chord(symbol) if isinstance(symbol, str) else symbol
    return target.matches(notes)
