from helpers import Rig

from mfl import srs
from mfl.exercises.ear import make_phrase
from mfl.theory import Key


def test_chord_probe_known_chord_is_graded_easy():
    rig = Rig({"kind": "chord", "skill": "chord/D", "symbol": "D", "mode": "new"})
    assert rig.ex.phase == "probe"
    rig.wait(1.0)
    rig.on(62, 66, 69)
    assert rig.ex.accepted and "know it" in rig.ex.feedback
    rig.off()
    assert rig.ex.done and rig.ex.result.grade == srs.EASY


def test_chord_probe_times_out_into_teaching_then_recall():
    rig = Rig({"kind": "chord", "skill": "chord/Bb", "symbol": "Bb", "mode": "new"})
    rig.wait(6.5)
    assert rig.ex.phase == "guided"
    assert rig.audio.demos(), "teaching starts with a demonstration"
    target = sorted(rig.ex.target)
    rig.on(*[n + 12 for n in target])  # same shape an octave up is fine
    assert rig.ex.accepted
    rig.off()
    assert rig.ex.phase == "recall"
    rig.on(62, 65, 70)  # first inversion from memory
    rig.off()
    assert rig.ex.done and rig.ex.result.grade == srs.GOOD


def test_chord_review_misses_bring_guidance_back():
    rig = Rig({"kind": "chord", "skill": "chord/D", "symbol": "D", "mode": "review"})
    for _ in range(2):
        rig.tap(62, 65, 69)  # D minor
    assert rig.ex.phase == "guided" and "Dm" in rig.ex.feedback
    rig.on(*rig.ex.target)
    rig.off()
    rig.tap(62, 66, 69)
    assert rig.ex.done and rig.ex.result.grade == srs.AGAIN


def test_chord_review_allows_bass_doubling_and_hint():
    rig = Rig({"kind": "chord", "skill": "chord/F", "symbol": "F", "mode": "review"})
    rig.ex.hint(rig.now)
    assert rig.ex.phase == "guided" and rig.ex.hints == 1
    rig.on(41, *rig.ex.voicing)  # left-hand root below the guided shape
    assert rig.ex.accepted


def test_held_keys_at_start_block_until_release():
    rig = Rig({"kind": "chord", "skill": "chord/C", "symbol": "C", "mode": "review"})
    rig.ex.blocked = True
    rig.on(60, 64, 67)
    assert not rig.ex.accepted
    rig.off()
    rig.on(60, 64, 67)
    assert rig.ex.accepted


def test_demo_waits_for_release_gap_and_yields_to_playing():
    rig = Rig({"kind": "chord", "skill": "chord/A", "symbol": "A", "mode": "review"})
    rig.on(57)
    rig.ex.hint(rig.now)  # asks for a demonstration while a key is held
    assert not rig.audio.demos()
    rig.off(57)
    rig.wait(0.5)
    assert not rig.audio.demos(), "no demonstration right after the learner releases"
    rig.wait(0.4)
    assert len(rig.audio.demos()) == 1
    rig.on(57)
    assert "demo" in rig.audio.stopped


def test_walk_accepts_any_voicing_and_legato_changes():
    rig = Rig({"kind": "walk", "skill": "prog/axis/C", "prog": "axis", "key": "C", "loops": ["symbols"]})
    rig.on(60, 64, 67)  # C
    rig.off(60, 64)
    rig.on(59, 62)  # G, keeping G held (legato)
    assert rig.ex.position == 2
    rig.off()
    rig.on(57, 60, 64)  # Am
    rig.off()
    rig.on(53, 57, 60)  # F
    assert rig.ex.done
    assert rig.ex.result.grade in (srs.GOOD, srs.EASY)
    assert rig.ex.distances


def test_walk_wrong_note_is_counted_once():
    rig = Rig({"kind": "walk", "skill": "prog/axis/C", "prog": "axis", "key": "C", "loops": ["roman"]})
    rig.on(61)
    rig.off()
    rig.on(62)
    rig.off()
    assert rig.ex.missed == {0}
    for chord in ((60, 64, 67), (59, 62, 67), (60, 64, 69), (60, 65, 69)):
        rig.on(*chord)
        rig.off()
    assert rig.ex.done and rig.ex.result.score == 0.75


def _playalong(item, play):
    rig = Rig(item)
    rig.wait(0.05)  # schedules after one tick with no keys held
    ex = rig.ex
    assert ex.t0 is not None
    for beat, chord_index in ex.expected:
        hit_time = ex.time_of(beat) + play(beat)
        if hit_time > rig.now:
            rig.wait(hit_time - rig.now, step=0.005)
        chord = ex.chords[chord_index][3]
        notes = ex.voicings[chord_index]
        rig.on(*notes)
        rig.wait(0.1, step=0.005)
        rig.off(*notes)
    rig.wait(ex.time_of(ex.total_beats) + 0.5 - rig.now)
    return rig


def test_playalong_scores_timing_and_learns_offset():
    item = {"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "pattern": "halves",
            "bpm": 90, "cue": "roman", "passes": 1}
    rig = _playalong(item, lambda beat: 0.02)
    ex = rig.ex
    assert ex.done
    assert ex.status.count("good") == len(ex.expected)
    assert ex.result.grade == srs.EASY
    assert 0 < rig.ctx.timing_offset < 0.02
    backing = [events for tag, events in rig.audio.played if tag == "backing"][0]
    assert any(e.instrument == "drums" for e in backing) and any(e.instrument == "bass" for e in backing)


def test_playalong_late_and_missing_hits_lower_the_grade():
    item = {"kind": "playalong", "skill": "groove/quarters", "prog": "axis", "key": "G", "pattern": "quarters",
            "bpm": 100, "cue": "symbols", "passes": 1, "listen": True}
    rig = _playalong(item, lambda beat: 0.16 if int(beat) % 2 else 0.0)
    ex = rig.ex
    assert ex.done and "late" in ex.status
    assert ex.result.grade <= srs.GOOD
    assert ex.learn_from == ex.count_in + len(ex.prog.bars) * ex.bpb  # example pass comes first


def wait_until_answerable(rig, limit=10.0):
    end = rig.now + limit
    while not rig.ex.can_answer(rig.now) and rig.now < end:
        rig.wait(0.05)
    assert rig.ex.can_answer(rig.now)


def test_degree_rounds_and_resolution():
    rig = Rig({"kind": "degrees", "skill": "ear/degrees/135", "key": "G", "level": "135", "rounds": 3})
    ex = rig.ex
    rig.wait(0.1)
    rig.on(ex.target)  # too early: the cadence is still playing
    assert ex.waiting_replay
    rig.off()
    for round_number in range(3):
        wait_until_answerable(rig)
        rig.tap(ex.target + 12)  # any octave
        assert len(ex.results) == round_number + 1
    assert ex.done
    assert ex.result.details["results"] == [True, True, True]
    # Each correct answer is followed by a stepwise resolution before the next target.
    second = rig.audio.demos()[-1]
    assert len(second) >= 2


def test_degree_wrong_twice_reveals():
    rig = Rig({"kind": "degrees", "skill": "ear/degrees/diatonic", "key": "C", "level": "diatonic", "rounds": 1})
    ex = rig.ex
    rig.wait(4.0)
    wrong = ex.target + 1 if (ex.target + 1) % 12 != ex.target % 12 else ex.target + 2
    rig.tap(wrong)
    rig.wait(4.0)
    rig.tap(wrong)
    assert ex.revealed
    rig.tap(ex.target)
    assert ex.done and ex.result.grade == srs.AGAIN


def test_echo_phrase_and_octave_shift():
    rig = Rig({"kind": "echo", "skill": "ear/echo/3", "key": "C", "length": 3, "rounds": 1})
    ex = rig.ex
    rig.wait(6.0)
    for note in ex.phrase:
        rig.tap(note - 12)
    assert ex.done and ex.result.grade == srs.EASY


def test_make_phrase_is_singable():
    import random
    key = Key.parse("D")
    for seed in range(30):
        phrase = make_phrase(key, 5, random.Random(seed))
        assert len(phrase) == 5
        assert all(n % 12 in key.scale.pcs for n in phrase)
        assert max(abs(a - b) for a, b in zip(phrase, phrase[1:])) <= 7
        assert phrase[-1] % 12 in {key.tonic.pc, key.scale.pcs[2], key.scale.pcs[4]}


def test_chord_ear_identifies_wrong_answer():
    rig = Rig({"kind": "chordear", "skill": "ear/chords/I-IV-V", "key": "C", "level": "I-IV-V", "rounds": 1})
    ex = rig.ex
    rig.wait(5.0)
    wrong = "IV" if ex.roman != "IV" else "V"
    rig.tap(*Key.parse("C").chord(wrong).notes and [n.pc + 60 for n in Key.parse("C").chord(wrong).notes])
    assert "You played" in ex.feedback
    rig.wait(5.0)
    rig.on(*ex.voicing)
    assert ex.answered
    rig.off()
    assert ex.done


def test_freeplay_names_chords_and_key():
    rig = Rig({"kind": "free", "skill": "free"})
    for chord in ((62, 66, 69), (67, 71, 74), (69, 73, 76), (62, 66, 69), (59, 62, 66), (67, 71, 74)):
        rig.on(*chord)
        rig.wait(0.3)
        rig.off()
    rig.on(55, 59, 62)
    view = rig.ex.view(rig.now)
    assert view.big == "G"
    assert rig.ex.key.name == "D major"
    assert "IV" in view.caption
    rig.ex.toggle_groove(rig.now)
    rig.wait(2.0)
    assert any(tag == "groove" for tag, _ in rig.audio.played)
