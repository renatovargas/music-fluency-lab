from helpers import Rig

from mfl import srs
from mfl.exercises.ear import make_phrase
from mfl.theory import Key


def test_new_chord_is_taught_first_and_never_advances_on_a_timer():
    rig = Rig({"kind": "chord", "skill": "chord/D", "symbol": "D", "mode": "new"})
    assert rig.ex.phase == "guided"
    rig.wait(1.0)
    assert rig.audio.demos(), "teaching starts with a demonstration"
    rig.wait(30.0)  # the learner is reading or thinking: nothing moves on
    assert rig.ex.phase == "guided" and not rig.ex.done
    rig.tap(62, 65, 69)  # D minor: told what to fix, still guided
    assert rig.ex.phase == "guided" and "highlighted" in rig.ex.feedback
    rig.on(62, 66, 69)
    assert rig.ex.accepted
    rig.off()
    assert rig.ex.phase == "recall" and not rig.ex.done
    rig.wait(30.0)
    assert not rig.ex.done
    rig.tap(66, 69, 74)
    assert rig.ex.done and rig.ex.result.grade == srs.GOOD


def test_new_chord_guide_then_recall_any_inversion():
    rig = Rig({"kind": "chord", "skill": "chord/Bb", "symbol": "Bb", "mode": "new"})
    rig.wait(1.0)
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


def test_playalong_waits_when_nothing_is_played():
    item = {"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "pattern": "whole",
            "bpm": 120, "cue": "symbols", "passes": 1}
    rig = Rig(item)
    rig.wait(0.05)
    ex = rig.ex
    assert ex.t0 is not None
    rig.wait(ex.time_of(ex.total_beats) + 0.5 - rig.now, step=0.05)
    assert not ex.done, "an untouched pass is not graded"
    assert ex.t0 is None and not ex.armed and "didn't hear you" in ex.feedback
    rig.wait(10.0, step=0.1)
    assert ex.t0 is None, "the band waits for the learner"
    rig.tap(60)
    rig.wait(0.05)
    assert ex.t0 is not None


def test_playalong_tempo_follows_learner_preference():
    from mfl.exercises import Context, build
    from helpers import FakeAudio

    ctx = Context(FakeAudio())
    ctx.set_tempo_scale(0.8)
    ex = build({"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "bpm": 70}, ctx)
    assert ex.bpm == 56 and "56 BPM" in " ".join(ex.intro()[2])
    assert ctx.set_tempo_scale(0.1) == 0.6


def test_every_exercise_explains_itself():
    from mfl.exercises import Context, build
    from helpers import FakeAudio

    ctx = Context(FakeAudio())
    items = [
        {"kind": "chord", "skill": "chord/C", "symbol": "C", "mode": "new"},
        {"kind": "chord", "skill": "chord/C", "symbol": "C", "mode": "review"},
        {"kind": "walk", "skill": "prog/axis/C", "prog": "axis", "key": "C", "loops": ["full", "symbols"],
         "demo": True},
        {"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "listen": True},
        {"kind": "degrees", "skill": "ear/degrees/135", "key": "C", "level": "135"},
        {"kind": "echo", "skill": "ear/echo/3", "key": "C", "length": 3},
        {"kind": "chordear", "skill": "ear/chords/I-IV-V", "key": "C", "level": "I-IV-V"},
    ]
    for item in items:
        heading, why, steps = build(item, ctx).intro()
        assert heading and len(why) > 40 and len(steps) >= 2, item["kind"]


def test_intro_explains_where_things_come_from():
    from mfl.exercises import Context, build
    from helpers import FakeAudio

    ctx = Context(FakeAudio())
    _, why, _ = build({"kind": "chord", "skill": "chord/F", "symbol": "F", "mode": "new"}, ctx).intro()
    assert "IV in C major" in why
    _, why, _ = build({"kind": "walk", "skill": "prog/axis/G", "prog": "axis", "key": "G"}, ctx).intro()
    assert "pop" in why and "D (V)" in why and "G major scale" in why


def test_playalong_two_bar_count_in_and_visual_offset():
    item = {"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "pattern": "halves",
            "bpm": 60, "cue": "symbols", "passes": 1}
    rig = Rig(item)
    rig.wait(0.05)
    ex = rig.ex
    assert ex.count_in == 8 and ex.chords[0][0] == 8
    clicks = [e for tag, events in rig.audio.played if tag == "backing" for e in events
              if e.instrument == "drums" and e.time < ex.time_of(ex.count_in)]
    assert len(clicks) == 6  # bar 1: beats 1 and 3; bar 2: every beat
    rig.wait(ex.time_of(5.2) - rig.now)
    view = ex.view(rig.now)
    assert view.big == "2" and "first chord: C" in view.caption
    rig.ctx.timing_offset = 0.1  # the learner hears everything 100 ms later
    assert abs(ex.view(rig.now).lane.now - (5.2 - 0.1 / ex.spb)) < 1e-6


def test_sync_measures_when_the_learner_hears_the_clicks():
    from mfl.exercises.sync import LEAD_IN, TAPS

    rig = Rig({"kind": "sync", "skill": "sync", "graded": False})
    rig.wait(0.05)
    ex = rig.ex
    for i in range(LEAD_IN, LEAD_IN + TAPS):
        rig.wait(ex.click_time(i) + 0.07 - rig.now, step=0.005)
        rig.tap(60, hold=0.05)
    rig.wait(ex.click_time(LEAD_IN + TAPS) + 0.5 - rig.now, step=0.05)
    assert ex.done and not ex.result.graded
    assert abs(rig.ctx.timing_offset - 0.07) < 0.01


def test_sync_handles_long_delays_and_hides_the_beat():
    from mfl.exercises.sync import LEAD_IN, TAPS

    rig = Rig({"kind": "sync", "skill": "sync", "graded": False})
    rig.wait(0.05)
    ex = rig.ex
    captions = set()
    for i in range(LEAD_IN, LEAD_IN + TAPS):
        rig.wait(ex.click_time(i) + 0.45 - rig.now, step=0.01)  # e.g. a Bluetooth speaker
        captions.add(ex.view(rig.now).caption)
        rig.tap(60, hold=0.05)
    rig.wait(ex.click_time(LEAD_IN + TAPS) + 0.5 - rig.now, step=0.05)
    assert ex.done and abs(rig.ctx.timing_offset - 0.45) < 0.01
    assert all(c.startswith("taps:") for c in captions), "the screen only counts taps"


def test_sync_uneven_taps_are_retried():
    from mfl.exercises.sync import LEAD_IN, TAPS

    rig = Rig({"kind": "sync", "skill": "sync", "graded": False})
    rig.wait(0.05)
    ex = rig.ex
    for k, i in enumerate(range(LEAD_IN, LEAD_IN + TAPS)):
        rig.wait(ex.click_time(i) + (0.0 if k % 2 else 0.5) - rig.now, step=0.01)
        rig.tap(60, hold=0.05)
    rig.wait(ex.click_time(LEAD_IN + TAPS) + 0.5 - rig.now, step=0.05)
    assert not ex.done and "uneven" in ex.feedback


def test_sync_without_taps_waits_to_retry():
    from mfl.exercises.sync import LEAD_IN, TAPS

    rig = Rig({"kind": "sync", "skill": "sync", "graded": False})
    rig.wait(0.05)
    rig.wait((LEAD_IN + TAPS + 1) * rig.ex.spb + 1, step=0.05)
    assert not rig.ex.done and rig.ex.t0 is None and "try again" in rig.ex.feedback


def wait_until_answerable(rig, limit=10.0):
    end = rig.now + limit
    while not rig.ex.can_answer(rig.now) and rig.now < end:
        rig.wait(0.05)
    assert rig.ex.can_answer(rig.now)


def test_degree_rounds_and_resolution():
    rig = Rig({"kind": "degrees", "skill": "ear/degrees/135", "key": "G", "level": "135", "rounds": 3})
    ex = rig.ex
    assert ex.teaching and ex.offset == 0  # anchored first: play home
    rig.tap(ex.target)
    assert not ex.teaching and not ex.results, "the anchor is not graded"
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
    rig.tap(ex.target)  # home
    wait_until_answerable(rig)
    wrong = ex.target + 1 if (ex.target + 1) % 12 != ex.target % 12 else ex.target + 2
    rig.tap(wrong)
    wait_until_answerable(rig)
    rig.tap(wrong)
    assert ex.revealed
    rig.tap(ex.target)
    assert ex.done and ex.result.grade == srs.AGAIN


def test_new_degrees_meet_each_note_before_the_quiz():
    rig = Rig({"kind": "degrees", "skill": "ear/degrees/135", "key": "C", "level": "135", "rounds": 2,
               "mode": "new"})
    ex = rig.ex
    met = []
    while ex.teaching:
        met.append(ex.offset)
        view = ex.view(rig.now)
        assert view.piano.target == frozenset({ex.target}) and "highlighted" in ex.feedback
        rig.tap(ex.target + 1)  # a wrong key during teaching costs nothing
        assert "highlighted" in ex.feedback and ex.teaching
        rig.tap(ex.target)
    assert met == [0, 4, 7] and not ex.results
    rig.wait(1.0)
    quiz = rig.audio.demos()[-1]
    tonic_then_target = [e.note for e in quiz][-2:]
    assert tonic_then_target[0] == ex.tonic_midi, "every quiz round plays home first"
    assert set(ex.view(rig.now).piano.marks.values()) >= {"do", "mi", "sol"}, "answers are marked"


def _orient(rig):
    """Play the scale up from home, as the echo exercise asks first."""
    ex = rig.ex
    assert ex.orienting and ex.view(rig.now).piano.target == frozenset({ex.scale[0]})
    for note in ex.scale:
        rig.tap(note)
    assert not ex.orienting and ex.phrase, "letting go after the scale starts the first melody"


def test_echo_orients_with_the_scale_first():
    rig = Rig({"kind": "echo", "skill": "ear/echo/3", "key": "G", "length": 3, "rounds": 1})
    ex = rig.ex
    rig.tap(ex.scale[0] + 1)  # a wrong key while orienting costs nothing
    assert ex.orienting and ex.scale_position == 0 and "lit key" in ex.feedback
    labels = ex.view(rig.now).piano.marks
    assert labels[ex.scale[0]] == "do" and labels[ex.scale[4]] == "sol"
    _orient(rig)
    assert not ex.results


def test_echo_phrase_and_octave_shift():
    rig = Rig({"kind": "echo", "skill": "ear/echo/3", "key": "C", "length": 3, "rounds": 1})
    ex = rig.ex
    _orient(rig)
    view = ex.view(rig.now)
    assert view.piano.target == frozenset({ex.phrase[0]}), "the first note is shown"
    assert all(ex.scale[0] <= n <= ex.scale[-1] for n in ex.phrase), "melodies stay in the labelled octave"
    wait_until_answerable(rig)
    for note in ex.phrase:
        rig.tap(note - 12)
    assert ex.done and ex.result.grade == srs.EASY


def test_echo_wrong_note_keeps_progress_and_lights_the_next_key():
    rig = Rig({"kind": "echo", "skill": "ear/echo/4", "key": "C", "length": 4, "rounds": 1})
    ex = rig.ex
    _orient(rig)
    wait_until_answerable(rig)
    rig.tap(ex.phrase[0])
    rig.tap(ex.phrase[1])
    wrong = ex.phrase[2] + 1 if ex.phrase[2] + 1 != ex.phrase[1] else ex.phrase[2] + 2
    rig.tap(wrong)
    assert ex.position == 2, "earlier notes still count"
    wait_until_answerable(rig)
    rig.tap(wrong)
    assert ex.revealed and ex.view(rig.now).piano.target == frozenset({ex.phrase[2]})
    rig.tap(ex.phrase[2])
    rig.tap(ex.phrase[3])
    assert ex.done and ex.result.grade == srs.AGAIN


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
