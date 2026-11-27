import asyncio
from collections import deque
import time

from helpers import FakeAudio

from mfl.storage import Progress
from mfl.ui import app as appmod


def test_app_runs_a_session_from_the_keyboard(tmp_path, monkeypatch):
    batches = deque()

    class FakeMidi:
        name = "Launchkey Mini simulator"

        def __init__(self, preferred):
            pass

        def poll(self):
            return batches.popleft() if batches else []

        def close(self):
            pass

    monkeypatch.setattr("mfl.midi.MidiInput", FakeMidi)

    def send(kind, *notes):
        batches.append([(kind, n, 100, time.perf_counter()) for n in notes])

    async def run():
        store = Progress(tmp_path / "progress.sqlite3")
        audio = FakeAudio()
        app = appmod.MFLApp(progress=store, audio=audio)
        async with app.run_test(size=(90, 40)) as pilot:
            await pilot.pause(0.1)
            assert "Play any key" in str(app.query_one("#feedback").render())
            send("on", 60)
            await pilot.pause(0.05)
            send("off", 60)
            await pilot.pause(0.1)
            practice = app.practice
            assert practice.state == "exercise" and practice.exercise.kind == "chord"
            send("on", 60, 64, 67)  # C is known: the probe accepts it
            await pilot.pause(0.05)
            assert ("on", 67, 100, "live") in audio.live
            send("off", 60, 64, 67)
            await pilot.pause(0.1)
            assert "✓" in str(app.query_one("#feedback").render())
            await pilot.press("i")
            assert audio.keys_instrument == "epiano" and store.setting("instrument") == "epiano"
            await pilot.press("minus")
            assert abs(audio.volume - 0.75) < 1e-6
            await pilot.press("s")
            await pilot.press("p")
            await pilot.pause(0.1)
            assert isinstance(app.screen, appmod.ProgressScreen)
            await pilot.press("escape")
            await pilot.press("q")

    asyncio.run(run())
