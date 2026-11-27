"""Free play: the end of every session. Play a song you love.

MFL listens without judging. It names the chords you play, estimates the
key from what it has heard, shows each chord's Roman numeral, and can add a
drum groove to play along with.
"""

from __future__ import annotations

from mfl.audio.engine import NoteEvent
from mfl.exercises.base import ChartView, Exercise, PianoView, View
from mfl.theory import GROOVES, estimate_key, harmonic_function, identify
from mfl.theory.keys import Key

GROOVE_ORDER = ("ballad", "pop", "rock", "latin", "bolero", "waltz")


class FreePlay(Exercise):
    kind = "free"
    block = "Play"
    timed = True

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.weights = [0.0] * 12
        self.last_decay = 0.0
        self.trail: list[str] = []
        self.current = None
        self.key: Key | None = None
        self.confidence = 0.0
        self.groove: str | None = None
        self.bpm = float(item.get("bpm", 76))
        self.scheduled_until = 0.0
        self.groove_start = 0.0
        self.notes_played = 0

    def start(self, now):
        super().start(now)
        self.last_decay = now
        self.say("Play anything you like: a song you love, an idea, a progression.", "info")

    def note_on(self, note, velocity, now):
        self.notes_played += 1
        self.weights[note % 12] += 1.0 + (0.6 if note == min(self.ctx.held) else 0.0)
        self._identify()

    def note_off(self, note, now):
        self._identify(record=False)

    def _identify(self, record: bool = True):
        held = self.ctx.held
        found = identify(held, spell=self._spell) if len(held) >= 2 else []
        self.current = found[0] if found else None
        if self.current is not None and record:
            symbol = self.current.symbol
            if not self.trail or self.trail[-1] != symbol:
                self.trail.append(symbol)
                self.trail = self.trail[-8:]
        estimate = estimate_key(self.weights)
        if estimate and sum(self.weights) >= 8:
            self.key, self.confidence = estimate

    def _spell(self, pc, quality):
        from mfl.theory.chords import default_root
        if self.key is not None and self.confidence > 0.6:
            return self.key.spell(pc)
        return default_root(pc, quality)

    def tick(self, now):
        # Slowly forget old notes so the key estimate follows modulations.
        elapsed = now - self.last_decay
        if elapsed > 0.5:
            factor = 0.5 ** (elapsed / 25.0)
            self.weights = [w * factor for w in self.weights]
            self.last_decay = now
        if self.groove is not None and now + 1.5 > self.scheduled_until:
            self._schedule_bar(self.scheduled_until)

    def _schedule_bar(self, start: float):
        groove = GROOVES[self.groove]
        beats = groove.get("beats", 4)
        spb = 60.0 / self.bpm
        events = [NoteEvent(start + beat * spb, drum, velocity, 0.1, "drums")
                  for beat, drum, velocity in groove["drums"] if beat < beats]
        self.ctx.backing(events, tag="groove")
        self.scheduled_until = start + beats * spb

    def toggle_groove(self, now):
        index = GROOVE_ORDER.index(self.groove) + 1 if self.groove in GROOVE_ORDER else 0
        self.ctx.stop_backing("groove")
        if index >= len(GROOVE_ORDER):
            self.groove = None
            self.say("Drums off.", "info")
            return
        self.groove = GROOVE_ORDER[index]
        self.scheduled_until = now + 0.3
        self.say(f"Drums: {self.groove} at {self.bpm:.0f} BPM. G changes style, [ and ] change tempo.", "info")

    def tempo(self, delta: float, now):
        self.bpm = max(50.0, min(160.0, self.bpm + delta))
        if self.groove is not None:
            self.say(f"Drums: {self.groove} at {self.bpm:.0f} BPM.", "info")

    def stop(self):
        super().stop()
        self.ctx.stop_backing("groove")

    def view(self, now) -> View:
        held = frozenset(self.ctx.held)
        if self.current is not None:
            big = self.current.symbol
            caption = self.current.name
            if self.key is not None:
                roman = self.key.analyze(self.current)
                if roman:
                    caption = f"{roman} in {self.key.short} · {harmonic_function(roman, self.key.mode)}"
        else:
            big, caption = "♪", "free play"
        key_text = f"Sounds like {self.key.name}" if self.key is not None and self.confidence > 0.55 else ""
        cells = self.trail[-8:] or ["·"]
        chart = ChartView(cells, len(cells) - 1 if self.trail else None, {}, "Your recent chords")
        piano = PianoView(held=held, tonic_pcs=frozenset({self.key.tonic.pc}) if self.key else frozenset())
        groove = f"Drums: {self.groove} {self.bpm:.0f} BPM" if self.groove else "Drums off"
        return View(block=self.block, title="Play a song you love", big=big, caption=caption,
                    lesson=f"Accompany yourself singing, or explore. {groove}. G: drums · [ ]: tempo · I: sound.",
                    key=key_text, piano=piano, chart=chart, feedback=self.feedback, tone=self.tone)
