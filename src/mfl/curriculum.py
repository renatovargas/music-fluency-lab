"""The curriculum: an ordered path of units, each a handful of skills.

Skill IDs are stable strings stored in the progress database:
  chord/<symbol>            play a chord from its symbol (any inversion)
  prog/<progression>/<key>  navigate a progression in a key
  groove/<pattern>          comp a rhythm pattern with the band
  ear/degrees/<level>       hear a scale degree, play it
  ear/echo/<length>         hear a short phrase, play it back
  ear/chords/<level>        hear a chord in a key, play it

The path starts in the learner's familiar keys (C, G, A minor), adds the
Andalusian cadence early for Latin repertoire, then spirals around the
circle of fifths, adding sevenths, borrowed chords and secondary dominants.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mfl.theory import PROGRESSIONS, Key, parse_chord


@dataclass(frozen=True)
class Skill:
    id: str
    kind: str  # chord, prog, groove, degrees, echo, chordear
    title: str
    unit: int
    params: tuple = field(default=())

    @property
    def p(self) -> dict:
        return dict(self.params)


@dataclass(frozen=True)
class Unit:
    index: int
    title: str
    key: str
    skills: tuple[Skill, ...]


# Ear-training vocabularies.
DEGREE_LEVELS = {
    "135": ("Do, mi, sol", "major", (0, 4, 7)),
    "diatonic": ("All seven major-scale degrees", "major", (0, 2, 4, 5, 7, 9, 11)),
    "minor": ("Minor-key degrees", "minor", (0, 2, 3, 5, 7, 8, 10, 11)),
    "chromatic": ("All twelve tones", "major", tuple(range(12))),
}
CHORD_EAR_LEVELS = {
    "I-IV-V": ("I, IV and V", ("I", "IV", "V")),
    "vi": ("I, IV, V and vi", ("I", "IV", "V", "vi")),
    "ii-iii": ("All diatonic triads", ("I", "ii", "iii", "IV", "V", "vi")),
    "color": ("Borrowed and secondary chords", ("I", "IV", "V", "vi", "♭VII", "iv", "V7/vi")),
}
ECHO_LEVELS = {3: "three-note phrases", 4: "four-note phrases", 5: "five-note phrases", 6: "six-note phrases"}


def _chord(symbol: str, unit: int) -> Skill:
    c = parse_chord(symbol)
    return Skill(f"chord/{c.ascii}", "chord", f"{c.symbol} — {c.name}", unit, (("symbol", c.ascii),))


def _prog(prog_id: str, key: str, unit: int) -> Skill:
    p = PROGRESSIONS[prog_id]
    k = Key.parse(key)
    return Skill(f"prog/{prog_id}/{k.ascii}", "prog", f"{p.name} in {k.name}", unit,
                 (("prog", prog_id), ("key", k.ascii)))


def _groove(pattern: str, unit: int) -> Skill:
    from mfl.theory import COMP_PATTERNS
    return Skill(f"groove/{pattern}", "groove", f"Rhythm: {COMP_PATTERNS[pattern].name}", unit,
                 (("pattern", pattern),))


def _degrees(level: str, unit: int) -> Skill:
    return Skill(f"ear/degrees/{level}", "degrees", f"Ear: {DEGREE_LEVELS[level][0]}", unit, (("level", level),))


def _echo(length: int, unit: int) -> Skill:
    return Skill(f"ear/echo/{length}", "echo", f"Ear: echo {ECHO_LEVELS[length]}", unit, (("length", length),))


def _chordear(level: str, unit: int) -> Skill:
    return Skill(f"ear/chords/{level}", "chordear", f"Ear: chords {CHORD_EAR_LEVELS[level][0]}", unit,
                 (("level", level),))


def _units() -> list[Unit]:
    spec = [
        ("Home base: C major", "C", lambda u: [
            _chord("C", u), _chord("F", u), _chord("G", u), _chord("Am", u),
            _prog("axis", "C", u), _degrees("135", u)]),
        ("The C major family", "C", lambda u: [
            _chord("Dm", u), _chord("Em", u), _prog("doowop", "C", u), _groove("halves", u), _echo(3, u)]),
        ("G major", "G", lambda u: [
            _chord("D", u), _chord("Bm", u), _prog("axis", "G", u), _prog("three-chord", "G", u),
            _chordear("I-IV-V", u)]),
        ("A minor and the Andalusian cadence", "Am", lambda u: [
            _chord("E", u), _prog("andalusian", "Am", u), _prog("minor-plagal", "Am", u),
            _groove("quarters", u), _degrees("diatonic", u)]),
        ("F major", "F", lambda u: [
            _chord("Bb", u), _chord("Gm", u), _prog("axis", "F", u), _prog("doowop", "F", u), _echo(4, u)]),
        ("D major", "D", lambda u: [
            _chord("A", u), _chord("F#m", u), _prog("axis", "D", u), _prog("mixolydian", "D", u),
            _groove("tresillo", u), _chordear("vi", u)]),
        ("E minor ballads", "Em", lambda u: [
            _chord("B", u), _prog("andalusian", "Em", u), _prog("minor-plagal", "Em", u),
            _groove("cinquillo", u)]),
        ("Seventh chords in C", "C", lambda u: [
            _chord("G7", u), _chord("Cmaj7", u), _chord("Am7", u), _chord("Dm7", u), _chord("Fmaj7", u),
            _prog("ii-V-I", "C", u), _degrees("minor", u)]),
        ("Secondary dominants and borrowed chords", "C", lambda u: [
            _chord("E7", u), _chord("Fm", u), _chord("Bb", u), _prog("latin-ballad", "C", u),
            _prog("borrowed-iv", "C", u), _prog("mixolydian", "C", u), _groove("pop8", u), _echo(5, u)]),
        ("B♭ major", "Bb", lambda u: [
            _chord("Eb", u), _chord("Cm", u), _chord("F7", u), _prog("axis", "Bb", u), _prog("circle", "Bb", u),
            _chordear("ii-iii", u)]),
        ("A major", "A", lambda u: [
            _chord("C#m", u), _chord("E7", u), _prog("axis", "A", u), _prog("doowop", "A", u),
            _groove("habanera", u)]),
        ("D minor boleros", "Dm", lambda u: [
            _chord("A7", u), _prog("bolero-minor", "Dm", u), _prog("andalusian", "Dm", u), _groove("waltz", u)]),
        ("Slash chords and walking bass", "C", lambda u: [
            _chord("G/B", u), _chord("C/G", u), _chord("C/E", u), _prog("descending-bass", "C", u),
            _prog("canon", "D", u), _groove("arpeggio", u)]),
        ("E♭ major", "Eb", lambda u: [
            _chord("Ab", u), _chord("Fm", u), _chord("Bb7", u), _prog("axis", "Eb", u), _prog("ii-V-I", "Eb", u),
            _degrees("chromatic", u)]),
        ("E major", "E", lambda u: [
            _chord("G#m", u), _chord("B7", u), _prog("axis", "E", u), _prog("three-chord", "E", u), _echo(6, u)]),
        ("Suspensions and colour", "G", lambda u: [
            _chord("Csus4", u), _chord("Gsus4", u), _chord("Dsus2", u), _chord("Cadd9", u),
            _prog("sus-release", "G", u), _prog("epic", "C", u), _chordear("color", u)]),
        ("Blues and turnarounds", "C", lambda u: [
            _chord("C7", u), _prog("blues", "C", u), _prog("turnaround", "F", u), _groove("charleston", u)]),
        ("A♭ major", "Ab", lambda u: [
            _chord("Db", u), _chord("Bbm", u), _chord("Eb7", u), _prog("axis", "Ab", u), _prog("doowop", "Ab", u)]),
        ("B major and C♯ minor", "B", lambda u: [
            _chord("F#", u), _chord("D#m", u), _prog("axis", "B", u), _prog("andalusian", "C#m", u)]),
        ("D♭ major", "Db", lambda u: [
            _chord("Gb", u), _chord("Ebm", u), _prog("axis", "Db", u), _prog("circle", "Db", u)]),
        ("F♯ minor and G minor", "F#m", lambda u: [
            _chord("C#", u), _chord("D7", u), _prog("bolero-minor", "F#m", u), _prog("bolero-minor", "Gm", u)]),
    ]
    units: list[Unit] = []
    seen: set[str] = set()
    for index, (title, key, make) in enumerate(spec):
        skills = tuple(s for s in make(index) if s.id not in seen)
        seen.update(s.id for s in skills)
        units.append(Unit(index, title, key, skills))
    return units


UNITS: list[Unit] = _units()
SKILLS: dict[str, Skill] = {s.id: s for unit in UNITS for s in unit.skills}


def skill(skill_id: str) -> Skill | None:
    return SKILLS.get(skill_id)


def introduced_keys(states: dict[str, dict]) -> list[str]:
    """Keys the learner has met through progressions (always includes C)."""
    keys = ["C"]
    for skill_id, state in states.items():
        s = SKILLS.get(skill_id)
        if s and s.kind == "prog" and state.get("reps"):
            k = s.p["key"]
            if k not in keys:
                keys.append(k)
    return keys
