import pytest

from mfl.theory import (
    PROGRESSIONS, Interval, Key, Note, Scale, close_voicings, comfortable_voicing, estimate_key, identify,
    lead_progression, matches_chord, note_name, parse_chord, parse_midi, voice_lead, voice_leading_distance,
)
from mfl.theory.chords import QUALITIES


def symbols(key, romans):
    return [Key.parse(key).chord(r).symbol for r in romans.split()]


def test_note_spelling_and_midi():
    assert note_name(60) == "C4" and note_name(70) == "Bb4" and note_name(66) == "F#4"
    assert note_name(61, unicode=True) == "D♭4"
    assert parse_midi("C4") == 60 and parse_midi("F#3") == 54 and parse_midi("Bb2") == 46
    assert Note.parse("B#").pc == 0 and Note.parse("Cb").pc == 11
    assert Note.parse("F#").enharmonic().text == "G♭"
    assert str(Note.parse("C").transpose(Interval.parse("m3"))) == "E♭"
    assert str(Note.parse("E").transpose(Interval.parse("A2"))) == "F𝄪".replace("𝄪", "♯♯")


def test_intervals():
    assert Interval.parse("m3").semitones == 3 and Interval.parse("P5").semitones == 7
    assert Interval.parse("A4").name == "augmented fourth"
    assert Interval.parse("M9").semitones == 14
    assert Note.parse("D").interval_to(Note.parse("F#")).short == "M3"
    assert Note.parse("B").interval_to(Note.parse("F")).short == "d5"


def test_scales_and_modes():
    assert [n.text for n in Scale(Note.parse("D")).notes] == ["D", "E", "F♯", "G", "A", "B", "C♯"]
    assert [n.text for n in Scale(Note.parse("F"), "major").notes][3] == "B♭"
    assert [n.text for n in Scale(Note.parse("A"), "harmonic minor").notes][-1] == "G♯"
    assert [n.text for n in Scale(Note.parse("G"), "mixolydian").notes][-1] == "F"
    assert len(Scale(Note.parse("C"), "blues").notes) == 6
    assert Scale(Note.parse("E"), "phrygian dominant").notes[2].text == "G♯"


def test_keys_signatures_and_diatonic_harmony():
    assert Key.parse("D").signature == 2 and Key.parse("Bb").signature == -2
    assert Key.parse("Em").signature == 1 and Key.parse("Dm").signature == -1
    assert Key.parse("C").relative.name == "A minor" and Key.parse("Am").relative.name == "C major"
    assert [c.symbol for _, c in Key.parse("A").diatonic()] == ["A", "Bm", "C♯m", "D", "E", "F♯m", "G♯°"]
    assert [c.symbol for _, c in Key.parse("Eb").diatonic(True)][:5] == ["E♭maj7", "Fm7", "Gm7", "A♭maj7", "B♭7"]


def test_roman_numerals():
    assert symbols("C", "I V vi IV") == ["C", "G", "Am", "F"]
    assert symbols("Am", "i ♭VII ♭VI V") == ["Am", "G", "F", "E"]
    assert symbols("C", "V7/vi V7/V iv bVII bVI") == ["E7", "D7", "Fm", "B♭", "A♭"]
    assert symbols("C", "I/3 V/7 I/5") == ["C/E", "G/B", "C/G"]
    assert symbols("F", "ii7 V7 Imaj7 viiø7 vii°7") == ["Gm7", "C7", "Fmaj7", "Eø7", "E°7"]
    assert symbols("G", "Isus4 IVsus2 Iadd9") == ["Gsus4", "Csus2", "Gadd9"]
    with pytest.raises(ValueError):
        Key.parse("C").chord("VIII")


def test_analysis_and_functions():
    c = Key.parse("C")
    assert c.analyze(parse_chord("G7")) == "V7"
    assert c.analyze(parse_chord("E7")) == "V7/vi"
    assert c.analyze(parse_chord("Bb")) == "♭VII"
    assert c.analyze(parse_chord("Fm")) == "iv"
    assert c.analyze(parse_chord("C/E")) == "I/3"
    assert Key.parse("F").analyze(parse_chord("Bb")) == "IV"
    assert "pulls home" in c.function("V7") and "borrowed" in c.function("iv")


def test_chord_parsing_spelling():
    assert parse_chord("F#m7b5").spelled == "F♯ A C E"
    assert parse_chord("Bbmaj7").spelled == "B♭ D F A"
    assert parse_chord("Cdim7").spelled == "C E♭ G♭ B♭♭"
    assert parse_chord("Ebm").symbol == "E♭m"
    assert parse_chord("G/B").bass.text == "B"
    assert parse_chord("C6/9").quality.suffix == "6/9"
    assert parse_chord("Am(add9)").quality.suffix == "madd9" or parse_chord("Amadd9").quality.suffix == "madd9"
    for alias in ("CM7", "CΔ7", "Cmaj7", "Cma7"):
        assert parse_chord(alias).quality.suffix == "maj7"
    assert len(QUALITIES) >= 35
    with pytest.raises(ValueError):
        parse_chord("Cxyz")


def test_chord_matching_inversions_doubling_and_slash():
    c = parse_chord("C")
    assert c.matches({60, 64, 67}) and c.matches({64, 67, 72}) and c.matches({48, 60, 64, 67, 72})
    assert not c.matches({60, 64, 68}) and not c.matches({60, 64})
    g7 = parse_chord("G7")
    assert g7.matches({55, 59, 65}) and g7.matches({55, 59, 62, 65})  # fifth may be omitted
    assert not g7.matches({59, 62, 67})
    slash = parse_chord("G/B")
    assert slash.matches({59, 62, 67}) and not slash.matches({55, 59, 62})
    assert matches_chord({57, 60, 64}, "Am") and not matches_chord({57, 60, 64, 67}, "Am")


def test_identify_from_midi():
    def name(notes):
        found = identify(notes)
        return found[0].symbol if found else None
    assert name({60, 64, 67}) == "C"
    assert name({64, 67, 72}) == "C/E"
    assert name({55, 59, 62, 65}) == "G7"
    assert name({57, 60, 64, 67}) == "Am7"
    assert name({59, 62, 65, 69}) == "Bø7"
    assert name({60, 65, 67}) == "Csus4"
    assert name({62, 66, 69, 73}) == "Dmaj7"
    assert name({60, 64, 70}) == "C7"  # dominant without fifth
    assert name({60, 67}) == "C5"
    assert name({60}) is None


def test_voicings_and_voice_leading():
    c = parse_chord("C")
    voicings = close_voicings(c, 55, 77)
    assert (60, 64, 67) in voicings and (64, 67, 72) in voicings and (55, 60, 64) in voicings
    assert all(55 <= n <= 77 for v in voicings for n in v)
    assert comfortable_voicing(parse_chord("D")) == (62, 66, 69)
    assert voice_lead((60, 64, 67), parse_chord("Am")) == (60, 64, 69)
    assert voice_lead((60, 64, 67), parse_chord("F")) == (60, 65, 69)
    assert voice_leading_distance({60, 64, 67}, {60, 64, 69}) == 2
    assert voice_leading_distance({60, 64, 67}, {59, 62, 65, 67}) is not None
    axis = lead_progression(PROGRESSIONS["axis"].chords(Key.parse("C")))
    moves = [voice_leading_distance(a, b) for a, b in zip(axis, axis[1:])]
    assert moves == [3, 5, 1]  # the minimal moves for C, G, Am, F


def test_progression_library_resolves_in_every_key():
    for prog in PROGRESSIONS.values():
        tonics = ("C", "G", "D", "A", "E", "F", "Bb", "Eb", "Ab")
        for tonic in tonics:
            key = Key.parse(tonic + ("m" if prog.mode == "minor" else ""))
            chords = prog.chords(key)
            assert len(chords) == len(prog.romans)
            assert all(c.symbol for c in chords)
    assert PROGRESSIONS["latin-ballad"].symbols(Key.parse("C"))[1] == "E7"
    timeline = PROGRESSIONS["turnaround"].timeline(Key.parse("C"))
    assert [t[0] for t in timeline[:4]] == [0, 2, 4, 6]


def test_key_estimation():
    c_major = [5, 0, 3, 0, 4, 2, 0, 4, 0, 2, 0, 1]
    key, score = estimate_key(c_major)
    assert key.name == "C major" and score > 0.8
    a_minor = [3, 0, 2, 0, 3, 1, 0, 1, 0, 5, 0, 1]
    assert estimate_key(a_minor)[0].name == "A minor"
    assert estimate_key([1] + [0] * 11) is None
