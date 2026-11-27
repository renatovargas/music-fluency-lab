"""Keys, diatonic harmony, Roman numerals, harmonic function and key finding.

Roman numerals use the pop/Berklee convention: degrees are always measured
against the *major* scale of the tonic. So in A minor the Andalusian cadence
is written i–♭VII–♭VI–V (Am–G–F–E), and ♭VII in C is B♭.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from mfl.theory.chords import BY_SUFFIX, Chord, _ALIASES
from mfl.theory.pitch import NATURAL_PC, Note, degree
from mfl.theory.scales import Scale

ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII")
MAJOR_TONICS = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MINOR_TONICS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")
CIRCLE_OF_FIFTHS = ("C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F")

_ROMAN = re.compile(
    r"^(?P<acc>[b#♭♯]*)(?P<num>VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)"
    r"(?P<q>°|o|ø|\+)?(?P<ext>[^/]*)(?:/(?P<target>.+))?$"
)


@dataclass(frozen=True)
class Key:
    tonic: Note
    mode: str = "major"  # "major" or "minor"

    @classmethod
    def parse(cls, text: str) -> Key:
        """``C``, ``F#``, ``Bb major``, ``Am``, ``C# minor``, ``Ebm``."""
        text = text.strip()
        match = re.fullmatch(r"([A-Ga-g][#♯b♭]?)\s*(m|min|minor|maj|major)?", text)
        if not match:
            raise ValueError(f"Invalid key {text!r}")
        mode = "minor" if match.group(2) in ("m", "min", "minor") else "major"
        return cls(Note.parse(match.group(1)), mode)

    @classmethod
    def from_pc(cls, pc: int, mode: str = "major") -> Key:
        table = MAJOR_TONICS if mode == "major" else MINOR_TONICS
        return cls(Note.parse(table[pc % 12]), mode)

    @property
    def scale(self) -> Scale:
        return Scale(self.tonic, "major" if self.mode == "major" else "natural minor")

    @property
    def name(self) -> str:
        return f"{self.tonic.text} {self.mode}"

    @property
    def ascii(self) -> str:
        return self.tonic.ascii + ("m" if self.mode == "minor" else "")

    @property
    def short(self) -> str:
        return self.tonic.text + ("m" if self.mode == "minor" else "")

    @property
    def relative(self) -> Key:
        if self.mode == "major":
            return Key(self.tonic.transpose(degree("6")), "minor")
        return Key(self.tonic.transpose(degree("b3")), "major")

    @property
    def parallel(self) -> Key:
        return Key(self.tonic, "minor" if self.mode == "major" else "major")

    @property
    def signature(self) -> int:
        """Sharps (positive) or flats (negative) in the key signature."""
        major = self if self.mode == "major" else self.relative
        return sum(n.alter for n in major.scale.notes)

    @property
    def signature_text(self) -> str:
        count = self.signature
        if count == 0:
            return "no sharps or flats"
        kind = "sharp" if count > 0 else "flat"
        return f"{abs(count)} {kind}{'s' if abs(count) > 1 else ''}"

    @property
    def prefer(self) -> str:
        return "flats" if self.signature < 0 else "sharps"

    def spell(self, pc: int) -> Note:
        """Spell any pitch class in this key's context."""
        for note in self.scale.notes:
            if note.pc == pc % 12:
                return note
        # Chromatic: prefer alterations matching the key signature direction.
        candidates = []
        for letter in range(7):
            alter = (pc - NATURAL_PC[letter] + 6) % 12 - 6
            if abs(alter) == 1:
                candidates.append(Note(letter, alter))
        flats = self.signature < 0
        candidates.sort(key=lambda n: (n.alter > 0) if flats else (n.alter < 0))
        return candidates[0] if candidates else Note.parse("C")

    def degree_note(self, number: int, alter: int = 0) -> Note:
        acc = "#" * alter if alter > 0 else "b" * -alter
        return self.tonic.transpose(degree(f"{acc}{number}"))

    def chord(self, roman: str) -> Chord:
        return roman_chord(self, roman)

    def diatonic(self, sevenths: bool = False) -> list[tuple[str, Chord]]:
        if self.mode == "major":
            romans = ("Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7") if sevenths else (
                "I", "ii", "iii", "IV", "V", "vi", "vii°")
        else:
            romans = ("i7", "iiø7", "♭IIImaj7", "iv7", "v7", "♭VImaj7", "♭VII7") if sevenths else (
                "i", "ii°", "♭III", "iv", "v", "♭VI", "♭VII")
        return [(r, self.chord(r)) for r in romans]

    def analyze(self, target: Chord) -> str | None:
        """Roman numeral for a chord in this key (``V7``, ``♭VII``, ``V7/vi``)."""
        numeral = _numeral_for(self, target)
        if numeral is None:
            return None
        diatonic_pcs = set(self.scale.pcs)
        if self.mode == "minor":
            diatonic_pcs.add(self.degree_note(7).pc)  # harmonic-minor leading tone
        dominant = target.quality.suffix in ("", "7", "9", "7b9", "13")
        if dominant and not target.pcs <= diatonic_pcs:
            for number in (2, 3, 4, 5, 6):
                dominant_root = self.degree_note(number).transpose(degree("5"))
                if dominant_root.pc != target.root.pc:
                    continue
                goal = self.diatonic()[number - 1] if self.mode == "major" else None
                goal_roman = goal[0] if goal else ROMANS[number - 1].lower()
                ext = "7" if "7" in target.quality.suffix else ""
                return f"V{ext}/{goal_roman}"
        return numeral

    def function(self, roman: str) -> str:
        return harmonic_function(roman, self.mode)

    def __str__(self) -> str:
        return self.name


def _numeral_for(key: Key, target: Chord) -> str | None:
    interval = key.tonic.interval_to(target.root)
    reference = NATURAL_PC[interval.steps]
    alter = (interval.semitones - reference + 6) % 12 - 6
    if abs(alter) > 1:
        return None
    acc = "♯" if alter > 0 else "♭" if alter < 0 else ""
    suffix = target.quality.suffix
    minor_third = target.quality.formula[1:2] == ("b3",)
    numeral = ROMANS[interval.steps]
    numeral = numeral.lower() if minor_third else numeral
    marks = {
        "": "", "m": "", "7": "7", "maj7": "maj7", "m7": "7", "dim": "°", "dim7": "°7", "m7b5": "ø7",
        "aug": "+", "sus4": "sus4", "sus2": "sus2", "6": "6", "m6": "6", "add9": "add9", "madd9": "add9",
        "9": "9", "m9": "9", "maj9": "maj9", "7sus4": "7sus4", "mMaj7": "maj7",
    }
    text = acc + numeral + marks.get(suffix, suffix)
    if target.bass is not None:
        bass_interval = key.tonic.interval_to(target.bass)
        b_alter = (bass_interval.semitones - NATURAL_PC[bass_interval.steps] + 6) % 12 - 6
        b_acc = "♯" if b_alter > 0 else "♭" if b_alter < 0 else ""
        text += f"/{b_acc}{bass_interval.steps + 1}"
    return text


@lru_cache(maxsize=2048)
def roman_chord(key: Key, roman: str) -> Chord:
    """Build a chord from a Roman numeral in a key.

    Uppercase = major, lowercase = minor, ``°`` diminished, ``ø`` half
    diminished, ``+`` augmented. Extensions follow: ``V7``, ``Imaj7``,
    ``ii7``, ``IVsus2``. ``/vi`` after a numeral is a secondary function
    (``V7/vi``); ``/3`` with digits puts that scale degree in the bass
    (``I/3`` = C/E, ``V/7`` = G/B in C).
    """
    match = _ROMAN.match(roman.strip())
    if not match:
        raise ValueError(f"Invalid Roman numeral {roman!r}")
    acc, num, mark, ext, target = match.group("acc", "num", "q", "ext", "target")
    bass = None
    if target:
        if re.fullmatch(r"[b#♭♯]*\d+", target):
            bass = key.tonic.transpose(degree(target))
        else:
            goal = roman_chord(key, target)
            key = Key(goal.root, "major")
    upper = num.isupper()
    number = ROMANS.index(num.upper()) + 1
    alter = sum(1 if a in "#♯" else -1 for a in acc)
    root = key.degree_note(number, alter)
    ext = ext.replace("♭", "b").replace("♯", "#")
    if mark in ("°", "o"):
        suffix = "dim7" if ext == "7" else "dim"
    elif mark == "ø":
        suffix = "m7b5"
    elif mark == "+":
        suffix = {"": "aug", "7": "aug7", "maj7": "maj7#5"}.get(ext, "aug")
    elif upper:
        suffix = ext
    else:
        suffix = {"": "m", "maj7": "mMaj7", "add9": "madd9", "7b5": "m7b5"}.get(ext, "m" + ext)
    quality = BY_SUFFIX.get(suffix) or _ALIASES.get(suffix)
    if quality is None:
        raise ValueError(f"Unknown chord extension {ext!r} in {roman!r}")
    return Chord(root, quality).with_bass(bass)


FUNCTION_NAMES = {"T": "tonic", "S": "subdominant", "D": "dominant"}


def harmonic_function(roman: str, mode: str = "major") -> str:
    """A short, plain-language description of what a chord does."""
    match = _ROMAN.match(roman.replace("♭", "b").replace("♯", "#"))
    if not match:
        return ""
    acc, num, mark, ext, target = match.group("acc", "num", "q", "ext", "target")
    if target and not re.fullmatch(r"[b#]*\d+", target):
        return f"secondary dominant: leans toward {target}"
    base = acc + num.upper()
    minor = num.islower()
    if mode == "minor":
        table = {
            "I": "home (tonic)", "bIII": "relative major (tonic colour)", "IV": "subdominant (borrowed major IV)",
            "V": "dominant: pulls home to i", "bVI": "subdominant colour", "bVII": "subtonic: leads to i or ♭III",
            "II": "pre-dominant", "VII": "leading-tone chord",
        }
        if base == "IV" and minor:
            return "subdominant: moves away from home"
        if base == "V" and minor:
            return "minor dominant: soft pull home"
        return table.get(base, "chromatic colour")
    if base == "I":
        return "home (tonic)"
    if base == "IV" and minor:
        return "borrowed minor iv: bittersweet ballad colour"
    table = {
        "II": "pre-dominant: prepares V", "III": "tonic substitute", "IV": "subdominant: moves away from home",
        "V": "dominant: tension that pulls home", "VI": "relative minor (tonic substitute)",
        "VII": "dominant function (leading tone)", "bVII": "borrowed ♭VII: rock/Mixolydian colour",
        "bVI": "borrowed ♭VI: epic, cinematic colour", "bIII": "borrowed ♭III: bluesy colour",
        "bII": "Neapolitan / tritone substitute",
    }
    return table.get(base, "chromatic colour")


# Krumhansl–Kessler key profiles (probe-tone ratings).
_MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def _correlation(xs, ys) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sxy / (sx * sy) if sx and sy else 0.0


def estimate_key(weights) -> tuple[Key, float] | None:
    """Estimate the key from 12 pitch-class weights (counts or durations).

    Returns (key, correlation) or None when there is too little information.
    """
    weights = list(weights)
    if len(weights) != 12 or sum(1 for w in weights if w > 0) < 3:
        return None
    best: tuple[float, Key] | None = None
    for tonic in range(12):
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            rotated = [profile[(pc - tonic) % 12] for pc in range(12)]
            score = _correlation(weights, rotated)
            if best is None or score > best[0]:
                best = (score, Key.from_pc(tonic, mode))
    assert best is not None
    return best[1], best[0]
