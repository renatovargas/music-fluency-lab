"""The practice screen. Playing the keyboard drives everything. The computer
keys are optional helpers (hint, skip, sound, volume, progress, quit)."""

from __future__ import annotations

import threading
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

from mfl import __version__
from mfl.audio import INSTRUMENT_NAMES, PLAYABLE, NullAudio
from mfl.session import Practice
from mfl.storage import Progress
from mfl.ui.render import big_text, chart, chips, lane, meter, piano

TONE = {"info": "#c8c8d8", "good": "bold #3fbf6a", "warn": "bold #e0b84a", "bad": "bold #e5534b"}
BIG_TONE = {"accent": "bold #e0b84a", "good": "bold #3fbf6a"}


class ProgressScreen(ModalScreen):
    BINDINGS = [Binding("escape,p,q", "dismiss", "Close")]
    DEFAULT_CSS = """
    ProgressScreen { align: center middle; }
    #report { width: 96; max-width: 100%; height: auto; max-height: 90%; border: round $accent;
              background: $surface; padding: 1 2; }
    """

    def __init__(self, store: Progress):
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        from mfl.report import report

        with VerticalScroll(id="report"):
            yield Static(report(self.store))
            yield Static(Text("\nEsc or P to close", "dim"))


class MFLApp(App):
    TITLE = "Musical Fluency Lab"
    CSS = """
    Screen { background: $background; }
    #top { height: 1; background: $panel; padding: 0 1; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    #body { padding: 0 2; height: 1fr; }
    #head { height: auto; margin-top: 1; }
    #title { width: 1fr; height: auto; }
    #key { width: auto; height: auto; color: $text-muted; }
    #bigrow { height: auto; margin-top: 1; }
    #big { width: auto; height: auto; }
    #caption { width: 1fr; height: 3; padding-left: 3; content-align: left middle; color: $text-muted; }
    #lesson { height: auto; margin-top: 1; color: $text-muted; }
    #chart, #lane, #chips, #piano { height: auto; margin-top: 1; }
    #feedback { height: auto; margin-top: 1; }
    """
    BINDINGS = [
        Binding("h", "hint", "Hint / replay"),
        Binding("s", "skip", "Skip"),
        Binding("i", "instrument", "Sound"),
        Binding("minus", "volume(-0.1)", "Vol −", show=False),
        Binding("plus,equals_sign", "volume(0.1)", "Vol +", show=False),
        Binding("g", "groove", "Drums", show=False),
        Binding("left_square_bracket", "tempo(-4)", "Slower", show=False),
        Binding("right_square_bracket", "tempo(4)", "Faster", show=False),
        Binding("r", "restart", "Restart exercise", show=False),
        Binding("p", "progress", "Progress"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, preferred: str | None = None, *, progress: Progress | None = None, sound: bool = True,
                 minutes: float | None = None, audio=None):
        super().__init__()
        self.preferred = preferred
        self.store = progress if progress is not None else Progress()
        self.want_sound = sound
        self.audio = audio
        self.audio_error = ""
        self.audio_starting = False
        self.minutes = minutes or float(self.store.setting("minutes", 30.0))
        self.midi = None
        self.midi_error = ""
        self.practice: Practice | None = None
        self.last_render = 0.0
        self.last_midi_try = 0.0
        self.dirty = True

    # ---- setup -------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="top")
        yield Static(id="status")
        with VerticalScroll(id="body"):
            with Horizontal(id="head"):
                yield Static(id="title")
                yield Static(id="key")
            with Horizontal(id="bigrow"):
                yield Static(id="big")
                yield Static(id="caption")
            yield Static(id="lesson")
            yield Static(id="chart")
            yield Static(id="lane")
            yield Static(id="chips")
            yield Static(id="piano")
            yield Static(id="feedback")
        yield Footer()

    def on_mount(self):
        theme = self.store.setting("theme", "tokyo-night")
        if theme in self.available_themes:
            self.theme = theme
        instrument = self.store.setting("instrument", "piano")
        volume = float(self.store.setting("volume", 0.85))
        if self.audio is None:
            self.audio = NullAudio()
            self.audio.set_instrument(instrument)
            self.audio.set_volume(volume)
            if self.want_sound:
                # Opening the device can take a second or two: do it off the UI thread.
                self.audio_error = ""
                self.audio_starting = True
                threading.Thread(target=self._open_audio, args=(instrument, volume), daemon=True).start()
        self.audio.set_instrument(instrument)
        self._connect_midi()
        self.practice = Practice(self.store, self.audio, minutes=self.minutes)
        self.set_interval(0.01, self._poll)
        self.render_all()

    def _open_audio(self, instrument: str, volume: float):
        try:
            from mfl.audio import open_audio
            audio = open_audio(instrument, volume)
        except Exception as error:  # visual practice still works
            message = (str(error).splitlines() or ["unavailable"])[0][:60]
            try:
                self.call_from_thread(self._audio_failed, message)
            except RuntimeError:
                pass
        else:
            try:
                self.call_from_thread(self._audio_ready, audio)
            except RuntimeError:  # the app quit while the device was opening
                audio.close()

    def _audio_ready(self, audio):
        self.audio_starting = False
        if self.practice is None or not self.is_running:
            audio.close()
            return
        self.audio = audio
        self.practice.audio = audio
        self.practice.ctx.audio = audio
        self.dirty = True

    def _audio_failed(self, message: str):
        self.audio_starting = False
        self.audio_error = message
        self.dirty = True

    def watch_theme(self, theme: str):
        if getattr(self, "store", None) is not None and theme:
            try:
                self.store.set_setting("theme", theme)
            except Exception:
                pass

    def _connect_midi(self):
        self.last_midi_try = time.perf_counter()
        try:
            from mfl.midi import MidiInput
            self.midi = MidiInput(self.preferred)
            self.midi_error = ""
        except Exception as error:
            self.midi = None
            self.midi_error = str(error)

    # ---- loop ------------------------------------------------------------------------------
    def _poll(self):
        now = time.perf_counter()
        practice = self.practice
        if practice is None:
            return
        if self.midi is None and now - self.last_midi_try > 2.0:
            self._connect_midi()
            self.dirty = True
        events = self.midi.poll() if self.midi is not None else []
        for kind, note, value, t in events:
            practice.on_midi(kind, note, value, t)
        practice.tick(now)
        exercise = practice.exercise
        timed = exercise is not None and exercise.timed
        interval = 1 / 30 if timed else 0.25
        if events or self.dirty or now - self.last_render >= interval:
            self.render_all()

    def render_all(self):
        practice = self.practice
        if practice is None:
            return
        self.dirty = False
        self.last_render = time.perf_counter()
        session = practice.view()
        view = session.view
        width = max(40, self.size.width - 6)

        # Top bar: blocks, position, time, streak.
        top = Text(no_wrap=True)
        top.append(" ♪ MFL ", "bold #10101a on #e0b84a")
        top.append("  ")
        for name, state in session.blocks:
            if state == "current":
                top.append(f" {name} ", "bold #10101a on #7aa2f7")
            elif state == "done":
                top.append(f" ✓ {name} ", "#3fbf6a")
            else:
                top.append(f" {name} ", "#7a7a8c")
            top.append(" ")
        top.append(f"  {min(session.position + 1, session.total)}/{session.total}", "#a0a0b0")
        top.append(f"  {session.minutes:.0f} of ~{session.planned_minutes:.0f} min", "#a0a0b0")
        if session.streak > 1:
            top.append(f"  streak {session.streak}", "#e0b84a")
        self._set("top", top)

        status = Text(no_wrap=True, overflow="ellipsis")
        if self.midi is not None:
            status.append(f"● {self.midi.name}", "#3fbf6a")
        else:
            status.append("○ Connect your keyboard… (retrying)", "#e0b84a")
        status.append("   ")
        if getattr(self.audio, "available", False):
            status.append(f"Sound: {INSTRUMENT_NAMES.get(self.audio.keys_instrument, '')}", "#c8c8d8")
            status.append(f"  vol {self.audio.volume:.0%} ", "#a0a0b0")
            status.append(meter(self.audio.peak, 8))
        elif self.audio_starting:
            status.append("Starting sound…", "#a0a0b0")
        elif self.audio_error:
            status.append(f"Audio off: {self.audio_error}", "#e5534b")
        else:
            status.append("Silent mode", "#a0a0b0")
        status.append(f"   v{__version__}", "#55556a")
        self._set("status", status)

        title = Text()
        if view.block and view.block != "Today":
            title.append(f"{view.block} · ", "#7aa2f7")
        title.append(view.title, "bold")
        if view.progress:
            title.append(f"   {view.progress}", "#a0a0b0")
        if view.listening:
            title.append("   ♪ listening…", "bold #5b8def")
        self._set("title", title)
        self._set("key", Text(view.key, "#a0a0b0"))

        big = big_text(view.big or "", BIG_TONE.get(view.big_tone, "bold")) if view.big else None
        if big is None and view.big:
            big = Text(view.big, BIG_TONE.get(view.big_tone, "bold"))
        self._set("big", big or "")
        self._set("caption", Text(view.caption, "italic #a0a0b0"))
        self._set("lesson", Text(view.lesson, "#9a9aac"))
        self._show("chart", chart(view.chart, width) if view.chart else None)
        self._show("lane", lane(view.lane, width) if view.lane else None)
        if view.ladder:
            labels, answer, wrong = view.ladder
            self._show("chips", chips(labels, answer, wrong))
        elif view.choices:
            self._show("chips", chips(view.choices))
        else:
            self._show("chips", None)
        self._show("piano", piano(view.piano, width) if view.piano else None)
        feedback = Text(view.feedback, TONE.get(view.tone, ""))
        if session.next_up:
            feedback.append(f"\nNext: {session.next_up}", "#7a7a8c")
        self._set("feedback", feedback)

    def _set(self, widget: str, value):
        self.query_one(f"#{widget}", Static).update(value)

    def _show(self, widget: str, value):
        node = self.query_one(f"#{widget}", Static)
        node.display = value is not None
        if value is not None:
            node.update(value)

    def on_resize(self):
        self.dirty = True

    # ---- actions ------------------------------------------------------------------------------
    def action_hint(self):
        self.practice.hint()
        self.dirty = True

    def action_skip(self):
        self.practice.skip()
        self.dirty = True

    def action_restart(self):
        self.practice.restart_exercise()
        self.dirty = True

    def action_instrument(self):
        current = self.audio.keys_instrument
        index = (PLAYABLE.index(current) + 1) % len(PLAYABLE) if current in PLAYABLE else 0
        self.audio.set_instrument(PLAYABLE[index])
        self.store.set_setting("instrument", PLAYABLE[index])
        self.notify(INSTRUMENT_NAMES[PLAYABLE[index]], timeout=1.5)
        self.dirty = True

    def action_volume(self, delta: float):
        self.audio.set_volume(round(self.audio.volume + delta, 2))
        self.store.set_setting("volume", self.audio.volume)
        self.dirty = True

    def action_groove(self):
        exercise = self.practice.exercise
        if exercise is not None and exercise.kind == "free":
            exercise.toggle_groove(time.perf_counter())
            self.dirty = True
        else:
            self.notify("Drums are available in free play at the end of the session.", timeout=2)

    def action_tempo(self, delta: float):
        exercise = self.practice.exercise
        if exercise is not None and exercise.kind == "free":
            exercise.tempo(delta, time.perf_counter())
            self.dirty = True

    def action_progress(self):
        self.push_screen(ProgressScreen(self.store))

    def on_unmount(self):
        if self.practice is not None:
            self.practice.close()
        if self.midi is not None:
            self.midi.close()
        if self.audio is not None:
            self.audio.close()
        self.store.close()
