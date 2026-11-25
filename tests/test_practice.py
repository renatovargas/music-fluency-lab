import asyncio
from collections import deque

from mfl.coach import SESSION, SessionCoach
from mfl.keyboard import piano
from mfl.midi import MidiInput
from mfl.storage import Progress
from mfl.tui import MFLApp


def play(coach, notes):
    for note in notes:
        coach.note_event("on", note)


def release(coach):
    for note in sorted(coach.held):
        coach.note_event("off", note)


def test_guidance_and_unassisted_history(tmp_path):
    progress = Progress(tmp_path / "progress.sqlite3")
    progress.record("chord", "Am", True, 1, {60, 64, 69}, None)
    coach = SessionCoach(progress)
    assert coach.phase == "guided"
    play(coach, (72, 76, 79, 79))
    assert coach.accepted
    assert coach.target == {72, 76, 79}
    coach.skip()
    coach.hint()
    coach.note_event("off", 72)
    assert coach.phase == "guided" and coach.accepted
    assert len(progress.last_attempts()) == 2
    release(coach)
    play(coach, (64, 67, 72))
    assert not coach.accepted
    release(coach)
    assert "Try again" in coach.feedback
    play(coach, (60, 64, 67))
    release(coach)
    assert coach.phase == "recall"
    play(coach, (64, 67, 72))
    release(coach)
    assert coach.step.chord == "Am"
    assert [(row[1], row[4]) for row in progress.last_attempts(include_exercise=True)] == [
        (1, "chord_recall"),
        (1, "chord_guided"),
        (0, "chord_guided"),
        (1, "chord_guided"),
        (1, "chord"),
    ]
    progress.close()


def test_recall_recovery_skip_and_restart_require_release(tmp_path):
    progress = Progress(tmp_path / "progress.sqlite3")
    coach = SessionCoach(progress, guided_successes=1)
    play(coach, (60, 64, 67))
    release(coach)
    for expected in ("recall", "guided"):
        play(coach, (60, 61, 62, 63))
        assert "Try again" in coach.feedback
        release(coach)
        assert coach.phase == expected

    play(coach, (60, 64, 67))
    release(coach)
    play(coach, (60, 64))
    coach.hint()
    play(coach, (67,))
    assert coach.phase == "guided" and coach.blocked
    assert not coach.accepted
    coach.skip()
    assert coach.step.chord == "Am"
    play(coach, (69,))
    assert not coach.accepted
    coach.restart()
    assert coach.blocked and coach.step.chord == "C"
    release(coach)
    play(coach, (60, 64, 67))
    assert coach.accepted
    assert sum(row[4] == "chord_skip" for row in progress.last_attempts(include_exercise=True)) == 1
    progress.close()


def test_completion_is_recorded_once(tmp_path):
    progress = Progress(tmp_path / "progress.sqlite3")
    coach = SessionCoach(progress, guided_successes=1)
    for step in SESSION:
        assert coach.step == step
        for _ in range(1 if step.recall_first else 2):
            play(coach, step.voicing)
            release(coach)
    assert coach.finished
    coach.skip()
    play(coach, (59, 62, 67))
    release(coach)
    assert progress.completed_sessions() == 1
    progress.close()


def test_piano_register_and_black_key_positions():
    rows = piano({59, 61, 96}, {59, 62, 67}, 65).plain.splitlines()
    assert rows[1][22 + 3] == "×"  # C-sharp 4, between C and D
    assert rows[2][19] == "●"  # B3
    assert rows[2][22 + 4] == "◆"  # D4
    assert rows[2][44 + 1] == "×"  # C7
    assert rows[3][::22] == "CCC"
    narrow = piano({59, 96}, None, 24).plain.splitlines()
    assert len(narrow) == 12
    assert [narrow[index].split()[0] for index in (3, 7, 11)] == ["C3", "C4", "C7"]
    assert "◆" not in "".join(narrow)


def test_midi_zero_velocity_note_on():
    messages = deque([([0x92, 60, 100], 0), ([0x92, 60, 0], 0), ([0x82, 64, 10], 0)])

    class Port:
        def get_message(self):
            return messages.popleft() if messages else None

    midi = MidiInput.__new__(MidiInput)
    midi.input = Port()
    assert midi.poll() == [("on", 60, 100), ("off", 60, 0), ("off", 64, 10)]


def test_tui_starts_playable_and_preserves_feedback(tmp_path, monkeypatch):
    batches = deque()
    demos = []
    sounded_notes = []

    class FakeAudio:
        def __init__(self):
            self.synth = self

        def demonstrate(self, notes):
            demos.append(notes)

        def stop_demo(self):
            pass

        def note_event(self, kind, note, velocity):
            sounded_notes.append((kind, note, velocity))

        def close(self):
            pass

    class FakeMidi:
        name = "Launchkey Mini simulator"

        def __init__(self, preferred):
            pass

        def poll(self):
            return batches.popleft() if batches else []

        def close(self):
            pass

    def send(app, kind, *notes):
        batches.append([(kind, note, 100) for note in notes])
        app.poll()

    async def practice():
        app = MFLApp(progress=Progress(tmp_path / "progress.sqlite3"))
        async with app.run_test(size=(34, 18)) as pilot:
            assert app.coach.phase == "guided"
            assert demos == [{60, 64, 67}]
            send(app, "on", 60, 61, 62)
            assert "Try again" in str(app.query_one("#feedback").render())
            send(app, "off", 60, 61, 62)
            assert "Try again" in str(app.query_one("#feedback").render())
            for _ in range(2):
                send(app, "on", 60, 64, 67)
                send(app, "off", 60, 64, 67)
            assert app.coach.phase == "recall"
            assert not app.query_one("#keyboard").display
            assert len(demos) == 1
            await pilot.press("h")
            assert app.coach.phase == "guided"
            assert app.query_one("#keyboard").display
            assert "◆" in str(app.query_one("#keyboard").render())
            assert demos == [{60, 64, 67}, {60, 64, 67}]
            send(app, "on", 60, 64, 67)
            assert app.coach.accepted
            assert sounded_notes[-3:] == [("on", note, 100) for note in (60, 64, 67)]

    monkeypatch.setattr("mfl.tui.MidiInput", FakeMidi)
    monkeypatch.setattr("mfl.tui.KeyboardAudio", FakeAudio)
    asyncio.run(practice())
