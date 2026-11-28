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
            assert practice.state == "intro"
            assert "play any key to start" in str(app.query_one("#feedback").render())
            send("on", 60)
            await pilot.pause(0.05)
            send("off", 60)
            await pilot.pause(0.1)
            assert practice.state == "exercise" and practice.exercise.kind == "chord"
            send("on", 60, 64, 67)  # copy the shape of C
            await pilot.pause(0.05)
            assert ("on", 67, 100, "live") in audio.live
            assert "✓" in str(app.query_one("#feedback").render())
            send("off", 60, 64, 67)
            await pilot.pause(0.1)
            await pilot.press("i")
            assert audio.keys_instrument == "epiano" and store.setting("instrument") == "epiano"
            await pilot.press("minus")
            assert abs(audio.volume - 0.75) < 1e-6 and store.setting("output_volume") == 0.75
            await pilot.press("plus")
            await pilot.press("plus")
            assert abs(audio.volume - 0.95) < 1e-6
            await pilot.press("left_square_bracket")
            assert practice.ctx.tempo_scale == 0.8
            await pilot.press("b")
            assert practice.state == "intro"
            await pilot.press("s")
            await pilot.press("p")
            await pilot.pause(0.1)
            assert isinstance(app.screen, appmod.ProgressScreen)
            await pilot.press("escape")
            await pilot.press("q")

    asyncio.run(run())


def test_dropouts_enlarge_the_audio_buffer(tmp_path, monkeypatch):
    class Midi:
        name = "fake"

        def __init__(self, preferred):
            pass

        def poll(self):
            return []

        def close(self):
            pass

    class CracklyAudio(FakeAudio):
        requested_latency = 0.045

        def reopen(self, latency):
            self.requested_latency = latency
            return latency

    monkeypatch.setattr("mfl.midi.MidiInput", Midi)

    async def run():
        store = Progress(tmp_path / "progress.sqlite3")
        audio = CracklyAudio()
        app = appmod.MFLApp(progress=store, audio=audio)
        async with app.run_test(size=(90, 40)) as pilot:
            app._check_dropouts(10.0)
            assert audio.requested_latency == 0.045
            audio.underflows = 5
            app._check_dropouts(13.0)
            assert abs(audio.requested_latency - 0.0675) < 0.001
            assert store.setting("audio_latency") == audio.requested_latency
            await pilot.press("q")

    asyncio.run(run())
