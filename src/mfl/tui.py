"""MIDI-driven practice screen."""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Static

from mfl.audio import KeyboardAudio
from mfl.coach import SESSION, SessionCoach
from mfl.keyboard import piano
from mfl.midi import MidiInput
from mfl.storage import Progress
from mfl.theory import note_name


class MFLApp(App):
    TITLE = "Musical Fluency Lab"
    CSS = """
    Screen { align-horizontal: center; }
    #panel { width: 76; max-width: 100%; height: 1fr; padding: 1 2; }
    #device, #audio, #counter, #legend { color: $text-muted; }
    #counter, #notes { margin-top: 1; }
    #task { text-style: bold; }
    #keyboard { margin-top: 1; }
    #feedback { margin-top: 1; min-height: 2; }
    """
    BINDINGS = [
        Binding("h", "hint", "Hint"),
        Binding("s", "skip", "Skip chord"),
        Binding("q", "quit", "Quit"),
        Binding("r", "restart", "Restart", show=False),
    ]

    def __init__(self, preferred: str | None = None, *, progress: Progress | None = None, sound: bool = True):
        super().__init__()
        self.preferred = preferred
        self.progress = progress if progress is not None else Progress()
        self.coach = SessionCoach(self.progress)
        self.midi: MidiInput | None = None
        self.sound = sound
        self.audio: KeyboardAudio | None = None
        self.demo_pending = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="panel"):
            yield Static("Connecting MIDI…", id="device", markup=False)
            yield Static(id="audio", markup=False)
            yield Static(id="counter", markup=False)
            yield Static(id="task", markup=False)
            yield Static(id="lesson", markup=False)
            yield Static(id="keyboard", markup=False)
            yield Static(id="legend", markup=False)
            yield Static(id="notes", markup=False)
            yield Static(id="feedback", markup=False)
        yield Footer()

    def on_mount(self):
        if self.sound:
            try:
                self.audio = KeyboardAudio()
            except Exception as error:
                self._show("audio", f"Audio unavailable · {error}")
        try:
            self.midi = MidiInput(self.preferred)
        except Exception as error:
            self._show("device", f"MIDI unavailable · {error}")
        else:
            self._show("device", f"MIDI connected · {self.midi.name}")
            self.set_interval(0.02, self.poll)
        self._cue_demo()
        self.render_step()

    def _cue_demo(self):
        if self.audio is not None:
            self.audio.synth.stop_demo()
            self.demo_pending = self.coach.phase == "guided" and not self.coach.finished
            self._play_pending_demo()

    def _play_pending_demo(self):
        if self.audio is not None and self.demo_pending and not self.coach.held:
            self.audio.synth.demonstrate(self.coach.target)
            self.demo_pending = False

    def _step_state(self):
        return self.coach.index, self.coach.phase, self.coach.finished

    def _show(self, widget: str, value: str | Text):
        self.query_one(f"#{widget}", Static).update(value)

    def on_resize(self):
        if self.is_mounted:
            self.call_after_refresh(self.render_step)

    def render_step(self):
        coach = self.coach
        if coach.finished:
            self._show("counter", "Session complete")
            self._show("task", "Play a song you love.")
            self._show("lesson", "Your practice is saved. Press R to start again or Q to quit.")
            for widget in ("keyboard", "legend", "notes", "feedback"):
                self._show(widget, "")
            return
        guided = coach.phase == "guided"
        self._show("counter", f"Chord {coach.index + 1} of {len(SESSION)} · {'Guided practice' if guided else 'Recall'}")
        self._show("task", f"Play {coach.step.name}")
        if guided:
            notes = "  ".join(map(note_name, sorted(coach.target)))
            cue = "Listen to the example, then play. H replays it.\n" if self.audio else ""
            self._show("lesson", f"{cue}{coach.step.lesson}\nHold {notes} together. The same shape in another octave works.")
        else:
            self._show("lesson", "Hold the three notes together from memory. Any inversion or octave works.")
        self.query_one("#keyboard").display = guided
        self.query_one("#legend").display = guided
        if guided:
            width = self.query_one("#panel", VerticalScroll).scrollable_content_region.width
            self._show("keyboard", piano(coach.held, coach.target, width))
            self._show("legend", "◆ Target   ● Held target   × Other held note")
        played = ", ".join(map(note_name, sorted(coach.held)))
        self._show("notes", f"Held · {played}" if played else "")
        self._show("feedback", "Release all keys to start." if coach.blocked else coach.feedback)

    def poll(self):
        if self.midi is None:
            return
        previous = self._step_state()
        events = self.midi.poll()
        for kind, note, velocity in events:
            if self.audio is not None:
                self.audio.synth.note_event(kind, note, velocity)
            self.coach.note_event(kind, note)
        if events:
            if previous != self._step_state():
                self._cue_demo()
            else:
                self._play_pending_demo()
            self.render_step()

    def action_hint(self):
        self.coach.hint()
        if not self.coach.accepted:
            self._cue_demo()
        self.render_step()

    def action_skip(self):
        previous = self._step_state()
        self.coach.skip()
        if previous != self._step_state():
            self._cue_demo()
        self.render_step()

    def action_restart(self):
        self.coach.restart()
        self._cue_demo()
        self.render_step()

    def on_unmount(self):
        if self.midi is not None:
            self.midi.close()
        if self.audio is not None:
            self.audio.close()
        self.progress.close()
