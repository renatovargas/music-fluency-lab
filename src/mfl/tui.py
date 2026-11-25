"""Miyagi-style guided chord practice with live keyboard feedback."""
import time
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Button
from textual.binding import Binding
from mfl.coach import SESSION
from mfl.midi import MidiInput
from mfl.storage import Progress
from mfl.theory import CHORDS, matches_chord, note_name, voice_leading_distance

# Chord examples deliberately fit the Launchkey Mini's usual two-octave range.
VOICINGS = {"C": (60,64,67), "Am": (60,64,69), "F": (60,65,69), "G": (59,62,67)}
EXPLANATIONS = {
 "C": "C major: C–E–G. Start with the three white keys shown below.",
 "Am": "A minor, first inversion: C–E–A. From C major, keep C and E; move G up to A.",
 "F": "F major, second inversion: C–F–A. From C–E–A, move E up one white key to F.",
 "G": "G major, first inversion: B–D–G. Listen to its pull back toward C.",
}

class MFLApp(App):
    TITLE = "Musical Fluency Lab"
    SUB_TITLE = "Your piano coach"
    CSS = """
    Screen { align: center middle; }
    #panel { width: 84; max-width: 96%; height: auto; padding: 1 2; border: round $accent; }
    #counter { color: $text-muted; margin-top: 1; }
    #task { text-style: bold; margin: 1 0; }
    #lesson { color: $text; min-height: 2; }
    #keyboard { margin: 1 0; background: $surface; padding: 1; }
    #feedback { min-height: 3; }
    #actions { height: 3; margin-top: 1; }
    Button { margin-right: 1; }
    """
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("r", "restart", "Restart")]

    def __init__(self, preferred: str | None = None):
        super().__init__()
        self.preferred = preferred
        self.progress = Progress()
        self.midi = None
        self.held: set[int] = set()
        self.index = 0
        self.phase = "show"  # show -> guided -> recall
        self.started = time.monotonic()
        self.previous_voicing: set[int] | None = None
        self.wait_release = False
        self.finished = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="panel"):
            yield Static("Connecting MIDI…", id="device")
            yield Static("", id="counter")
            yield Static("", id="task")
            yield Static("", id="lesson")
            yield Static("", id="keyboard")
            yield Static("", id="feedback")
            with Horizontal(id="actions"):
                yield Button("I've looked — let me try", id="next", variant="primary")
                yield Button("Show me again", id="hint")
                yield Button("Skip chord", id="skip")
        yield Footer()

    def on_mount(self):
        try:
            self.midi = MidiInput(self.preferred)
            self.query_one("#device", Static).update(f"MIDI connected: {self.midi.name}")
            self.set_interval(0.02, self.poll)
        except Exception as e:
            self.query_one("#device", Static).update(f"MIDI unavailable: {e}")
        self.render_step()

    def keyboard_view(self, show_target: bool) -> str:
        # Two chromatic octaves, C4 to B5. Visual feedback reflects real MIDI pitches.
        target = set(VOICINGS[SESSION[self.index].chord]) if show_target else set()
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        out = []
        for base in (60,72):
            parts = []
            for i, name in enumerate(names):
                n = base + i
                if n in self.held and n in target:
                    mark = "[bold green]●[/]"
                elif n in self.held:
                    mark = "[bold yellow]●[/]"
                elif n in target:
                    mark = "[bold cyan]◆[/]"
                else:
                    mark = "·"
                parts.append(mark)
            out.append(f"{'4' if base==60 else '5'}  " + " ".join(parts))
        return "[bold]C C# D D# E F F# G G# A A# B[/]\n" + "\n".join(out) + "\n[dim]◆ target  ● played  (each row is one octave; C4 = MIDI 60)[/]"

    def render_step(self):
        next_button = self.query_one("#next", Button)
        if self.finished:
            self.query_one("#counter", Static).update("SESSION COMPLETE")
            self.query_one("#task", Static).update("Beautiful. Now go play a song you love.")
            self.query_one("#lesson", Static).update("Your attempts are saved. Restart with R or quit with Q.")
            self.query_one("#keyboard", Static).update("")
            self.query_one("#feedback", Static).update("")
            next_button.disabled = True
            return
        step = SESSION[self.index]
        self.query_one("#counter", Static).update(f"SESSION {self.progress.completed_sessions()+1} · CHORD {self.index+1}/{len(SESSION)} · {self.phase.upper()}")
        self.query_one("#task", Static).update(step.instruction)
        if self.phase == "show":
            self.query_one("#lesson", Static).update(EXPLANATIONS[step.chord] + "\nLook at the highlighted notes, then press the button to try.")
            next_button.label = "I've looked — let me try"
            next_button.disabled = False
        elif self.phase == "guided":
            self.query_one("#lesson", Static).update("Play the highlighted notes together. Green means correct; yellow means another note. Release to continue.")
            next_button.label = "Hide hints — test recall"
            next_button.disabled = False
        else:
            self.query_one("#lesson", Static).update("No target notes now. Recall the chord from memory. Play any inversion, then release.")
            next_button.label = "Show the answer"
            next_button.disabled = False
        self.refresh_feedback()
        self.started = time.monotonic()

    def refresh_feedback(self):
        if self.finished:
            return
        target = set(VOICINGS[SESSION[self.index].chord])
        visible = self.phase != "recall"
        self.query_one("#keyboard", Static).update(self.keyboard_view(visible))
        if self.wait_release:
            return
        if not self.held:
            msg = "[dim]Listening for your keyboard…[/]"
        elif visible:
            correct = len(self.held & target)
            missing = ", ".join(note_name(n) for n in sorted(target - self.held))
            msg = f"Correct target notes: {correct}/3" + (f" · Still needed: {missing}" if missing else "")
        else:
            msg = "You played: " + ", ".join(note_name(n) for n in sorted(self.held))
        self.query_one("#feedback", Static).update(msg)

    def advance(self):
        self.held.clear()
        self.wait_release = False
        if self.index == len(SESSION)-1:
            self.finished = True
            self.progress.mark_session_complete()
        else:
            self.index += 1
            self.phase = "show" if self.index < 4 else "recall"
        self.render_step()

    def poll(self):
        if not self.midi:
            return
        events = self.midi.poll()
        if not events:
            return
        for kind, note, velocity in events:
            if kind == "on":
                self.held.add(note)
            else:
                self.held.discard(note)
            if self.wait_release:
                if not self.held:
                    self.advance()
                continue
            if self.finished or self.phase == "show" or kind != "on" or len(self.held) < 3:
                continue
            chord = SESSION[self.index].chord
            # Guided mode teaches a specific voice-leading voicing; recall accepts any inversion.
            success = self.held == set(VOICINGS[chord]) if self.phase == "guided" else matches_chord(self.held, chord)
            if success:
                current = set(self.held)
                distance = voice_leading_distance(self.previous_voicing, current) if self.previous_voicing else None
                self.progress.record("chord", chord, True, time.monotonic()-self.started, current, distance)
                self.previous_voicing = current
                self.wait_release = True
                self.query_one("#feedback", Static).update("[bold green]✓ That's it! Release the keys to continue.[/]")
            elif len(self.held) >= 3:
                self.query_one("#feedback", Static).update("[yellow]Not quite. Release the notes and try again, or reveal the guide.[/]")
        if not self.wait_release and not self.finished:
            self.refresh_feedback()
        elif not self.finished:
            self.query_one("#keyboard", Static).update(self.keyboard_view(self.phase != "recall"))

    def on_button_pressed(self, event: Button.Pressed):
        if self.finished:
            return
        if event.button.id == "next":
            if self.phase == "show":
                self.phase = "guided"
            elif self.phase == "guided":
                self.phase = "recall"
            else:
                self.phase = "show"
            self.render_step()
        elif event.button.id == "hint":
            self.phase = "show"
            self.render_step()
        elif event.button.id == "skip":
            self.progress.record("chord", SESSION[self.index].chord, False, time.monotonic()-self.started, set(self.held), None)
            self.advance()

    def action_restart(self):
        self.held.clear()
        self.index = 0
        self.phase = "show"
        self.previous_voicing = None
        self.wait_release = False
        self.finished = False
        self.render_step()

    def on_unmount(self):
        if self.midi:
            self.midi.close()
        self.progress.close()
