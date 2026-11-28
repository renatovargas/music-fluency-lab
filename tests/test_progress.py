from datetime import date, timedelta
import sqlite3

from helpers import Clock, FakeAudio

from mfl import srs
from mfl.planner import estimate_minutes, plan_session
from mfl.session import Practice, streak
from mfl.storage import Progress

TODAY = date(2026, 11, 27)


def legacy_db(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE attempts (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, exercise TEXT NOT NULL, "
               "chord TEXT NOT NULL, success INTEGER NOT NULL, seconds REAL NOT NULL, voicing TEXT NOT NULL, "
               "distance INTEGER)")
    rows = [("2026-11-24T10:00:00", "chord_recall", "C", 1), ("2026-11-24T10:01:00", "chord_recall", "Am", 1),
            ("2026-11-24T10:02:00", "chord_guided", "F", 1), ("2026-11-24T10:03:00", "chord", "G", 1),
            ("2026-11-24T10:04:00", "session_complete", "", 1)]
    for ts, ex, chord, ok in rows:
        db.execute("INSERT INTO attempts (timestamp,exercise,chord,success,seconds,voicing,distance) "
                   "VALUES (?,?,?,?,1,'',NULL)", (ts, ex, chord, ok))
    db.commit()
    db.close()


def test_migration_keeps_legacy_rows_and_seeds_skills(tmp_path):
    path = tmp_path / "progress.sqlite3"
    legacy_db(path)
    store = Progress(path)
    assert set(store.skills()) == {"chord/C", "chord/Am", "chord/G"}  # guided-only F is not seeded
    assert store.completed_sessions() == 1
    assert len(store.last_attempts()) == 4
    store.close()
    again = Progress(path)  # reopening is idempotent
    assert len(again.skills()) == 3
    again.close()


def test_srs_intervals_grow_and_lapse():
    state = None
    day = TODAY
    intervals = []
    for _ in range(4):
        state = srs.review(state, "chord/D", srs.GOOD, day)
        intervals.append(state["interval"])
        day = date.fromisoformat(state["due"])
    assert intervals == sorted(intervals) and intervals[-1] > 10
    lapsed = srs.review(state, "chord/D", srs.AGAIN, day)
    assert lapsed["interval"] == 1 and lapsed["lapses"] == 1 and lapsed["ease"] < state["ease"]
    assert srs.is_due(lapsed, day + timedelta(days=1))
    assert 0.85 < srs.retention(state, date.fromisoformat(state["due"])) < 0.95


def test_first_plan_teaches_then_ends_with_free_play():
    plan = plan_session({}, TODAY)
    kinds = [i["kind"] for i in plan]
    assert kinds[-1] == "free"
    assert plan[0]["mode"] == "new" and plan[0]["skill"] == "chord/C"
    assert {i["block"] for i in plan[:-1]} == {"Learn", "Navigate"}
    new = [i for i in plan if i.get("mode") == "new"]
    assert sum(0.5 if i["kind"] == "chord" else 1 for i in new) <= 5
    practice = [i for i in plan if i.get("mode") == "practice"]
    assert practice and all(i["graded"] is False and i["listen"] for i in practice)


def test_plan_reviews_due_items_and_respects_budget():
    states = {}
    for skill in ("chord/C", "chord/F", "chord/G", "chord/Am", "prog/axis/C", "ear/degrees/135"):
        states[skill] = srs.review(None, skill, srs.GOOD, TODAY - timedelta(days=3))
    plan = plan_session(states, TODAY)
    blocks = [i["block"] for i in plan]
    assert blocks.count("Warm-up") == 4
    assert "Navigate" in blocks and "Ear" in blocks
    assert sum(estimate_minutes(i) for i in plan) <= 34
    nav = next(i for i in plan if i["block"] == "Navigate")
    assert nav["kind"] == "walk" and nav["loops"] == ["symbols", "roman"]


def test_progression_reviews_climb_toward_play_along_without_chart():
    state = None
    for _ in range(5):
        state = srs.review(state, "prog/axis/C", srs.GOOD, TODAY)
    from mfl.curriculum import SKILLS
    from mfl.planner import prog_item
    import random
    item = prog_item(SKILLS["prog/axis/C"], state, random.Random(1), {"prog/axis/C": state}, "review")
    assert item["kind"] == "playalong" and item["cue"] == "none" and item["bpm"] >= 76


def test_streak_allows_rest_days():
    days = ["2026-11-20", "2026-11-21", "2026-11-24", "2026-11-26"]
    assert streak(days, TODAY) == 4
    assert streak(["2026-11-01"], TODAY) == 0


def play(practice, clock, notes, hold=0.2):
    for n in notes:
        practice.on_midi("on", n, 90, clock())
    clock.advance(hold)
    practice.tick(clock())
    for n in notes:
        practice.on_midi("off", n, 0, clock())


def test_session_flow_records_results_and_resumes(tmp_path):
    path = tmp_path / "progress.sqlite3"
    store = Progress(path)
    clock = Clock()
    audio = FakeAudio()
    practice = Practice(store, audio, today=TODAY, clock=clock, seed=3)
    assert practice.state == "welcome"
    assert practice.view().view.feedback == "Play any key to begin."
    play(practice, clock, [60])
    assert practice.state == "intro", "a new kind of exercise is explained first"
    assert "Learn a new chord: C" in practice.view().view.lesson
    clock.advance(20.0)
    practice.tick(clock())
    assert practice.state == "intro", "and waits for the learner"
    play(practice, clock, [60])
    assert practice.state == "exercise" and practice.exercise.kind == "chord"
    assert practice.exercise.chord.symbol == "C"
    clock.advance(1.0)
    play(practice, clock, [60, 64, 67])  # copy the shape
    play(practice, clock, [64, 67, 72])  # then from memory
    assert practice.state == "between"
    done = practice.view().view
    assert "✓" in done.feedback and done.title == "Exercise complete" and done.piano is None
    assert "Nothing to play" in done.lesson and "Next:" in done.lesson
    clock.advance(2.0)
    practice.tick(clock())
    assert practice.state == "between", "the completion screen stays long enough to read"
    clock.advance(1.5)
    practice.tick(clock())
    assert practice.position == 1
    assert store.skill("chord/C")["last_grade"] == srs.GOOD
    if practice.state == "intro":
        play(practice, clock, [60])
    assert practice.state == "exercise"
    practice.skip(clock())
    assert practice.position == 2
    practice.close()
    store.close()

    store = Progress(path)
    resumed = Practice(store, FakeAudio(), today=TODAY, clock=clock)
    assert resumed.resumed and resumed.position == 2
    assert "Welcome back" in resumed.view().view.title
    store.close()


def test_failed_new_item_returns_later_in_session(tmp_path):
    store = Progress(tmp_path / "progress.sqlite3")
    clock = Clock()
    practice = Practice(store, FakeAudio(), today=TODAY, clock=clock, seed=3)
    play(practice, clock, [60])
    play(practice, clock, [60])  # past the intro card
    length = len(practice.plan)
    ex = practice.exercise
    ex.mode = "review"  # force the strict review grading path
    ex.phase = "recall"
    for _ in range(2):
        play(practice, clock, [60, 63, 67])  # C minor, twice
    play(practice, clock, sorted(ex.target))
    play(practice, clock, [64, 67, 72])
    assert practice.last_result.grade == srs.AGAIN
    assert len(practice.plan) == length + 1
    assert practice.plan[practice.position + 2]["skill"] == "chord/C"
    store.close()


def test_back_repeat_and_tempo(tmp_path):
    store = Progress(tmp_path / "progress.sqlite3")
    clock = Clock()
    practice = Practice(store, FakeAudio(), today=TODAY, clock=clock, seed=3)
    play(practice, clock, [60])
    play(practice, clock, [60])
    first = practice.exercise.chord.symbol
    play(practice, clock, sorted(practice.exercise.target))
    play(practice, clock, sorted(practice.exercise.target))
    assert practice.state == "between" and "R: do it again" in practice.view().view.feedback
    practice.restart_exercise(clock())  # repeat the one just finished, straight away
    assert practice.state == "exercise" and practice.position == 0 and practice.exercise.chord.symbol == first
    practice.skip(clock())
    assert practice.position == 1
    practice.back(clock())  # back one step, with the explanation again
    assert practice.state == "intro" and practice.position == 0
    practice.back(clock())
    assert practice.position == 0
    assert store.open_session(TODAY.isoformat())["position"] == 0
    assert practice.change_tempo(-0.05) == 0.8 and store.setting("tempo_scale") == 0.8
    store.close()


def test_sound_check_comes_before_the_first_band_exercise(tmp_path):
    store = Progress(tmp_path / "progress.sqlite3")
    store.set_setting("audio_latency", 0.045)
    plan = [{"kind": "chord", "skill": "chord/C", "symbol": "C", "mode": "new", "block": "Learn"},
            {"kind": "playalong", "skill": "prog/axis/C", "prog": "axis", "key": "C", "block": "Navigate"},
            {"kind": "free", "skill": "free", "block": "Play", "mode": "free"}]
    store.create_session(TODAY.isoformat(), plan)
    practice = Practice(store, FakeAudio(), today=TODAY, clock=Clock())
    assert [i["kind"] for i in practice.plan] == ["chord", "sync", "playalong", "free"]
    store.set_setting("sync", {"offset": 0.05, "latency": 0.045})
    assert practice.sync_needed(), "a v1 check (eyes could lead) is redone"
    store.set_setting("sync", {"offset": 0.05, "latency": 0.045, "version": 2})
    assert not practice.sync_needed()
    assert abs(practice.nudge_timing(0.02) - 0.02) < 1e-9  # fresh Context offset starts at 0
    assert store.setting("sync")["version"] == 2 and abs(store.setting("timing_offset") - 0.02) < 1e-9
    store.set_setting("audio_latency", 0.0675)  # buffer raised: check again
    assert practice.sync_needed()
    store.close()


def test_pedal_and_pads_go_to_audio_not_exercises(tmp_path):
    store = Progress(tmp_path / "progress.sqlite3")
    clock = Clock()
    audio = FakeAudio()
    practice = Practice(store, audio, today=TODAY, clock=clock)
    practice.on_midi("pedal", 64, 127, clock())
    practice.on_midi("pad", 36, 100, clock())
    assert ("pedal", 1, 0, "live") in audio.live and ("on", 36, 100, "pads") in audio.live
    assert practice.state == "welcome" and not practice.ctx.held
    store.close()
