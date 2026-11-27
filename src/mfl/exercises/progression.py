"""Progressions: walk through them at your own pace, then play them in time
with a virtual band while the chord chart gradually disappears."""

from __future__ import annotations

from dataclasses import dataclass, field
import statistics

from mfl import srs
from mfl.audio.engine import NoteEvent
from mfl.exercises.base import ChartView, Exercise, LaneView, PianoView, View, chord_events
from mfl.theory import (
    COMP_PATTERNS, GROOVES, PROGRESSIONS, Key, bass_note, harmonic_function, lead_progression, movement_report,
    voice_lead, voice_leading_distance,
)
from mfl.theory.rhythm import CLICK_HI, CLICK_LO

CUE_WORDS = {
    "full": "Chart and keyboard guide",
    "symbols": "Chord symbols only",
    "roman": "Roman numerals only. Work out each chord in the key",
    "none": "No chart. Remember the progression",
}


def cue_cell(cue: str, roman: str, symbol: str, revealed: bool = False) -> str:
    if revealed or cue in ("full", "symbols"):
        return symbol
    if cue == "roman":
        return roman
    return "·"


class WalkExercise(Exercise):
    """Untimed: play each chord when ready. Common tones may stay held."""

    kind = "walk"
    block = "Navigate"

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.prog = PROGRESSIONS[item["prog"]]
        self.key = Key.parse(item["key"])
        self.loops: list[str] = list(item.get("loops", ["symbols"]))
        self.romans = self.prog.romans
        self.chords = self.prog.chords(self.key)
        self.steps = [(loop, i) for loop in range(len(self.loops)) for i in range(len(self.chords))]
        self.position = 0
        self.previous: tuple[int, ...] | None = None
        self.played_previous: frozenset | None = None
        self.missed: set[int] = set()
        self.hinted: set[int] = set()
        self.latencies: list[float] = []
        self.distances: list[int] = []
        self.step_started = 0.0
        self.blocked = bool(ctx.held)
        self.listen = bool(item.get("demo"))
        self.last_move = ""
        self.statuses: dict[int, str] = {}

    @property
    def loop(self) -> int:
        return self.steps[min(self.position, len(self.steps) - 1)][0]

    @property
    def index(self) -> int:
        return self.steps[min(self.position, len(self.steps) - 1)][1]

    @property
    def cue(self) -> str:
        return self.loops[self.loop]

    @property
    def current(self):
        return self.chords[self.index]

    def suggestion(self) -> tuple[int, ...]:
        return voice_lead(self.previous, self.current, self.ctx.low, self.ctx.high)

    def _demo(self, now):
        voicings = lead_progression(self.chords, self.ctx.low, self.ctx.high)
        events, t = [], 0.0
        for c, v in zip(self.chords, voicings):
            events += chord_events(v, t, 0.95, 74)
            events.append(NoteEvent(t, bass_note(c), 70, 0.95))
            t += 1.0
        self.ctx.demo(events, now)

    def start(self, now):
        super().start(now)
        self.step_started = now
        if self.listen:
            self._demo(now)
            self.say(f"Listen to {self.prog.name.lower()} in {self.key.name}. Join in when ready.", "info")
        else:
            self.say("Play each chord when you're ready. Keep common tones held.", "info")

    def note_on(self, note, velocity, now):
        if self.blocked or self.done:
            return
        target = self.current
        held = self.ctx.held
        if target.matches(held):
            self._accept(now)
            return
        carried = self.played_previous is not None and note % 12 in {n % 12 for n in self.played_previous}
        if note % 12 not in target.pcs and not carried and self.position not in self.missed:
            self.missed.add(self.position)
            self.statuses[self.position] = "miss"
            self.say(f"That note isn't in {target.symbol if self.cue in ('full', 'symbols') else 'this chord'}.",
                     "warn")

    def note_off(self, note, now):
        # Lifting a wrong note can leave the right chord sounding.
        if not self.blocked and not self.done and self.ctx.held and self.current.matches(self.ctx.held):
            self._accept(now)

    def released(self, now):
        self.blocked = False

    def _accept(self, now):
        held = frozenset(self.ctx.held)
        if self.loops[self.loop] != "full" or len(self.loops) == 1:
            self.latencies.append(now - self.step_started)
        if self.played_previous is not None:
            distance = voice_leading_distance(self.played_previous, held)
            if distance is not None:
                self.distances.append(distance)
            self.last_move = movement_report(self.played_previous, held)
        self.statuses.setdefault(self.position, "good")
        roman = self.romans[self.index]
        self.say(f"✓ {self.current.symbol} ({roman}) · {self.last_move}" if self.last_move else
                 f"✓ {self.current.symbol} ({roman})", "good")
        self.played_previous = held
        self.previous = tuple(sorted(held))
        self.position += 1
        self.step_started = now
        if self.position >= len(self.steps):
            self._complete(now)
        elif self.index == 0:
            self.say(f"Again, now with: {CUE_WORDS[self.cue].lower()}.", "info")

    def hint(self, now):
        if self.done:
            return
        if self.position not in self.hinted:
            self.hinted.add(self.position)
            self.hints += 1
            self.statuses[self.position] = "hint"
        if self.cue in ("full",):
            self._demo(now)

    def _complete(self, now):
        graded_steps = [p for p, (loop, _) in enumerate(self.steps) if self.loops[loop] != "full"] or \
            list(range(len(self.steps)))
        clean = sum(1 for p in graded_steps if p not in self.missed and p not in self.hinted)
        accuracy = clean / len(graded_steps)
        median = statistics.median(self.latencies) if self.latencies else 0.0
        hints = sum(1 for p in graded_steps if p in self.hinted)
        if accuracy >= 0.95 and hints == 0 and median < 2.0:
            grade = srs.EASY
        elif accuracy >= 0.8 and hints <= 1:
            grade = srs.GOOD
        elif accuracy >= 0.5:
            grade = srs.HARD
        else:
            grade = srs.AGAIN
        moves = f" · avg movement {statistics.mean(self.distances):.1f} semitones" if self.distances else ""
        summary = f"{clean}/{len(graded_steps)} clean changes · median {median:.1f} s per chord{moves}"
        self.finish(now, grade, accuracy, summary,
                    {"median": round(median, 2), "accuracy": round(accuracy, 3), "cues": self.loops})

    def view(self, now) -> View:
        cue = self.cue
        revealed = self.position in self.hinted
        cells = [cue_cell(cue, r, c.symbol, revealed and i == self.index) for i, (r, c) in
                 enumerate(zip(self.romans, self.chords))]
        statuses = {i: s for p, s in self.statuses.items() for (loop, i) in [self.steps[p]] if loop == self.loop}
        chart = ChartView(cells, self.index, statuses,
                          f"{self.prog.name} · {self.key.name} · pass {self.loop + 1} of {len(self.loops)}")
        show_guide = cue == "full" or revealed
        held = frozenset(self.ctx.held)
        if show_guide:
            target = frozenset(self.suggestion())
            piano = PianoView(held=held, target=target, good_pcs=self.current.pcs,
                              roots=frozenset(n for n in target if n % 12 == self.current.root.pc))
        else:
            piano = PianoView(held=held, tonic_pcs=frozenset({self.key.tonic.pc}))
        if cue in ("full", "symbols") or revealed:
            big, caption = self.current.symbol, f"{self.romans[self.index]} · {harmonic_function(self.romans[self.index], self.key.mode)}"
        elif cue == "roman":
            big, caption = self.romans[self.index], harmonic_function(self.romans[self.index], self.key.mode)
        else:
            big, caption = f"{self.index + 1}", f"chord {self.index + 1} of {len(self.chords)}"
        feedback, tone = ("Release all keys to begin.", "info") if self.blocked else (self.feedback, self.tone)
        return View(block=self.block, title="Walk the progression", big=big, caption=caption,
                    lesson=self.prog.about if self.mode == "new" and self.loop == 0 else CUE_WORDS[cue] + ".",
                    key=f"Key: {self.key.name}", piano=piano, chart=chart, feedback=feedback, tone=tone,
                    progress=f"{self.position}/{len(self.steps)}",
                    listening=bool(self.ctx.demo_handle and self.ctx.demo_handle.state == "playing"))


@dataclass
class Hit:
    time: float
    notes: set = field(default_factory=set)
    target: int | None = None  # index into expected
    error: float = 0.0


class PlayAlongExercise(Exercise):
    """Timed comping with drums and bass. Scores timing and harmony per hit."""

    kind = "playalong"
    block = "Navigate"
    timed = True
    CLUSTER = 0.06

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.prog = PROGRESSIONS[item["prog"]]
        self.key = Key.parse(item["key"])
        self.pattern = COMP_PATTERNS[item.get("pattern", "whole")]
        self.bpb = self.pattern.beats_per_bar
        self.bpm = float(item.get("bpm", 70))
        self.spb = 60.0 / self.bpm
        self.cue = item.get("cue", "symbols")
        self.groove = item.get("groove") or self.pattern.groove
        self.listen_passes = 1 if item.get("listen") else 0
        self.passes = int(item.get("passes", 2))
        timeline = self.prog.timeline(self.key, self.bpb)
        prog_beats = len(self.prog.bars) * self.bpb
        self.prog_beats = prog_beats
        self.count_in = self.bpb
        # Chords across the whole performance: (start beat, length, roman, chord).
        self.chords = []
        for p in range(self.listen_passes + self.passes):
            for start, length, roman, c in timeline:
                self.chords.append((self.count_in + p * prog_beats + start, length, roman, c))
        self.learn_from = self.count_in + self.listen_passes * prog_beats
        self.total_beats = self.count_in + (self.listen_passes + self.passes) * prog_beats
        self.expected: list[tuple[float, int]] = []  # (beat, chord index)
        self.status: list[str] = []
        for index, (start, length, _, _) in enumerate(self.chords):
            if start < self.learn_from:
                continue
            bar_start = start - (start - self.count_in) % self.bpb
            for onset in self.pattern.onsets:
                beat = bar_start + onset
                if start <= beat < start + length:
                    self.expected.append((beat, index))
                    self.status.append("upcoming")
        self.voicings = lead_progression([c for *_, c in self.chords], ctx.low, ctx.high)
        self.hits: list[Hit] = []
        self.t0: float | None = None
        self.revealed = False
        self.errors: list[float] = []

    def beat_at(self, now: float) -> float:
        return (now - self.t0) / self.spb if self.t0 is not None else -self.count_in

    def time_of(self, beat: float) -> float:
        return self.t0 + beat * self.spb

    def chord_index_at(self, beat: float) -> int:
        for i, (start, length, _, _) in enumerate(self.chords):
            if start <= beat < start + length:
                return i
        return 0 if beat < self.count_in else len(self.chords) - 1

    def start(self, now):
        super().start(now)
        self.say(f"{self.pattern.name} at {self.bpm:.0f} BPM. Count-in: {self.bpb} clicks.", "info")

    def _schedule(self, now):
        self.t0 = now + 0.5
        events: list[NoteEvent] = []
        for beat in range(self.count_in):
            events.append(NoteEvent(self.time_of(beat), CLICK_HI if beat == 0 else CLICK_LO, 100, 0.05, "drums"))
        groove = GROOVES.get(self.groove, GROOVES["ballad"])
        bars = int((self.total_beats - self.count_in) / self.bpb)
        for bar in range(bars):
            base = self.count_in + bar * self.bpb
            for beat, drum, velocity in groove["drums"]:
                if beat < self.bpb:
                    events.append(NoteEvent(self.time_of(base + beat), drum, velocity, 0.1, "drums"))
            bass_beats = [b for b in groove["bass"] if b < self.bpb]
            for k, beat in enumerate(bass_beats):
                index = self.chord_index_at(base + beat)
                c = self.chords[index][3]
                nxt = bass_beats[k + 1] if k + 1 < len(bass_beats) else self.bpb
                events.append(NoteEvent(self.time_of(base + beat), bass_note(c), 92, (nxt - beat) * self.spb * 0.9,
                                        "bass"))
        # The example pass: the piano plays the pattern itself.
        for index, (start, length, _, c) in enumerate(self.chords):
            if start >= self.learn_from:
                break
            bar_start = start - (start - self.count_in) % self.bpb
            voicing = self.voicings[index]
            for k, onset in enumerate(self.pattern.onsets):
                beat = bar_start + onset
                if not start <= beat < start + length:
                    continue
                nxt = self.pattern.onsets[k + 1] if k + 1 < len(self.pattern.onsets) else self.bpb
                dur = (nxt - onset) * self.spb * 0.9
                if self.pattern.single_tones:
                    order = list(voicing) + list(voicing[1:-1])[::-1]
                    notes = [order[k % len(order)]]
                else:
                    notes = voicing
                for n in notes:
                    events.append(NoteEvent(self.time_of(beat), n, 74, dur, "keys"))
        self.ctx.backing(events)

    def note_on(self, note, velocity, now):
        if self.t0 is None or self.done:
            return
        if self.hits and now - self.hits[-1].time < self.CLUSTER:
            hit = self.hits[-1]
            hit.notes.add(note)
            self._judge(hit)
            return
        hit = Hit(now, {note})
        self.hits.append(hit)
        beat = self.beat_at(now)
        if beat < self.learn_from - 0.5:
            hit.target = -1  # warming up during count-in or the example
            return
        window = min(0.45, 0.4 * self.spb)
        best = None
        for i, (b, _) in enumerate(self.expected):
            if self.status[i] != "upcoming":
                continue
            error = now - self.time_of(b) - self.ctx.timing_offset
            if abs(error) <= window and (best is None or abs(error) < abs(best[1])):
                best = (i, error)
        if best is not None:
            hit.target, hit.error = best
            self.errors.append(now - self.time_of(self.expected[best[0]][0]))
        self._judge(hit)

    def _judge(self, hit: Hit):
        if hit.target is None or hit.target < 0:
            return
        _, chord_index = self.expected[hit.target]
        c = self.chords[chord_index][3]
        pcs_held = {n % 12 for n in hit.notes}
        harmonic = pcs_held <= set(c.pcs) and (self.pattern.single_tones or len(pcs_held) >= 2)
        if not harmonic:
            self.status[hit.target] = "wrong"
        elif abs(hit.error) <= 0.05:
            self.status[hit.target] = "good"
        elif abs(hit.error) <= 0.11:
            self.status[hit.target] = "ok"
        else:
            self.status[hit.target] = "early" if hit.error < 0 else "late"

    def tick(self, now):
        if self.done:
            return
        if self.t0 is None:
            if not self.ctx.held:
                self._schedule(now)
            return
        window = min(0.45, 0.4 * self.spb)
        for i, (b, _) in enumerate(self.expected):
            if self.status[i] == "upcoming" and now > self.time_of(b) + window + self.ctx.timing_offset:
                self.status[i] = "missed"
        if now >= self.time_of(self.total_beats) + 0.2:
            self._complete(now)

    def hint(self, now):
        if not self.revealed:
            self.revealed = True
            self.hints += 1

    def stop(self):
        super().stop()
        self.ctx.stop_backing()

    def _complete(self, now):
        total = len(self.expected) or 1
        on_time = sum(1 for s in self.status if s in ("good", "ok")) / total
        played = [s for s in self.status if s not in ("missed", "upcoming")]
        harmony = sum(1 for s in played if s != "wrong") / (len(played) or 1)
        coverage = len(played) / total
        score = 0.55 * on_time + 0.3 * harmony * coverage + 0.15 * coverage
        if score >= 0.88 and self.hints == 0:
            grade = srs.EASY
        elif score >= 0.72:
            grade = srs.GOOD
        elif score >= 0.5:
            grade = srs.HARD
        else:
            grade = srs.AGAIN
        details = {"on_time": round(on_time, 3), "harmony": round(harmony, 3), "coverage": round(coverage, 3),
                   "bpm": self.bpm, "pattern": self.pattern.id, "cue": self.cue}
        summary = f"On time {on_time:.0%} · right chords {harmony:.0%}"
        if len(self.errors) >= 4:
            median = statistics.median(self.errors)
            spread = statistics.pstdev(self.errors)
            details.update(median_ms=round(median * 1000), spread_ms=round(spread * 1000))
            summary += f" · steadiness ±{spread * 1000:.0f} ms"
            if abs(median) > 0.025:
                summary += f" · tend to play {abs(median) * 1000:.0f} ms {'early' if median < 0 else 'late'}"
            # Learn the learner's (and the audio device's) systematic offset slowly.
            self.ctx.save_timing_offset(0.8 * self.ctx.timing_offset + 0.2 * median)
        self.ctx.stop_backing()
        self.finish(now, grade, score, summary, details)

    def view(self, now) -> View:
        beat = self.beat_at(now)
        index = self.chord_index_at(max(beat, self.count_in))
        _, _, roman, current = self.chords[index]
        cue = "symbols" if self.revealed else self.cue
        listening = beat < self.learn_from
        # Chart: one pass of the progression.
        per_pass = len(self.prog.romans)
        local = (index % per_pass)
        cells = [cue_cell(cue, r, c.symbol) for r, c in
                 zip(self.prog.romans, self.prog.chords(self.key))]
        if self.t0 is None:
            phase_text = "Get ready"
        elif beat < 0:
            phase_text = "Get ready"
        elif beat < self.count_in:
            phase_text = f"Count-in {int(beat) + 1}"
        elif listening:
            phase_text = "Listen: the band and the example"
        else:
            p = int((beat - self.learn_from) // self.prog_beats) + 1
            phase_text = f"Your turn · pass {min(p, self.passes)} of {self.passes}"
        chart = ChartView(cells, local if beat >= self.count_in else None, {}, f"{self.prog.name} · {self.key.name}")
        # Lane: current bar and the next.
        bar_index = max(0, int((max(beat, 0)) // self.bpb))
        window_start = bar_index * self.bpb
        expected = [(b, s) for (b, _), s in zip(self.expected, self.status)
                    if window_start - 0.01 <= b < window_start + 2 * self.bpb]
        if listening:
            for i, (start, length, _, _) in enumerate(self.chords):
                if start >= self.learn_from:
                    break
                bar_start = start - (start - self.count_in) % self.bpb
                for onset in self.pattern.onsets:
                    b = bar_start + onset
                    if start <= b < start + length and window_start <= b < window_start + 2 * self.bpb:
                        expected.append((b, "example"))
        strays = [self.beat_at(h.time) for h in self.hits
                  if h.target is None and window_start <= self.beat_at(h.time) < window_start + 2 * self.bpb]
        labels = [(start, cue_cell(cue, r, c.symbol)) for start, _, r, c in self.chords
                  if window_start <= start < window_start + 2 * self.bpb]
        lane = LaneView(self.bpb, window_start, 2 * self.bpb, beat, expected, strays, labels, phase_text)
        held = frozenset(self.ctx.held)
        if cue == "full":
            target = frozenset(self.voicings[index])
            piano = PianoView(held=held, target=target, good_pcs=current.pcs)
        else:
            piano = PianoView(held=held, good_pcs=current.pcs if cue != "none" else None)
        if cue in ("full", "symbols"):
            big, caption = current.symbol, roman
        elif cue == "roman":
            big, caption = roman, ""
        else:
            big, caption = "♪", f"bar {int((beat - self.count_in) // self.bpb) % len(self.prog.bars) + 1}" if beat >= self.count_in else ""
        lesson = f"{self.pattern.about}  Count: {self.pattern.counting}"
        return View(block=self.block, title=f"Play along · {self.pattern.name}", big=big, caption=caption,
                    lesson=lesson, key=f"Key: {self.key.name} · {self.bpm:.0f} BPM", piano=piano, chart=chart,
                    lane=lane, feedback=self.feedback if beat < self.count_in else phase_text,
                    tone="info", listening=listening)
