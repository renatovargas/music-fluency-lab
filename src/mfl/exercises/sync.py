"""Sound check: tap along with clicks to measure when the learner hears them.

Speakers, PipeWire/CoreAudio buffers and the keyboard all add delay that
software cannot see. Tapping along to sound alone (nothing moves on screen)
measures it directly. The median offset lines up the play-along lane with
what the learner hears and centres the timing judgement on it.
"""

from __future__ import annotations

import statistics

from mfl.audio.engine import NoteEvent
from mfl.exercises.base import Exercise, PianoView, View
from mfl.theory.rhythm import CLICK_HI, CLICK_LO

BPM = 60  # one click per second: delays up to ~0.8 s are unambiguous
LEAD_IN = 4  # clicks to listen to before tapping
TAPS = 8  # clicks to tap along with
NEEDED = 5  # matched taps for a usable measurement
MAX_SPREAD = 0.15  # seconds; less steady tapping than this is retried
VERSION = 2  # v1 showed progress dots at scheduled times, so eyes could lead


def save_sync(store, offset: float, latency: float | None):
    if store is not None:
        store.set_setting("sync", {"offset": round(offset, 4), "latency": latency, "version": VERSION})


class SyncExercise(Exercise):
    kind = "sync"
    block = "Navigate"
    timed = True

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.spb = 60.0 / BPM
        self.t0: float | None = None
        self.taps: list[float] = []
        self.armed = True
        self.tries = 0

    def intro(self):
        return ("Quick sound check (about 15 seconds)",
                "Speakers and audio software add a small delay that I can't see. Measuring it lines up the "
                "moving lane in band exercises with what you actually hear.",
                [f"You'll hear {LEAD_IN} clicks, one per second. Just listen.",
                 f"Then tap any key along with the next {TAPS} clicks. Close your eyes if it helps: "
                 "nothing on screen moves with the clicks.",
                 "That's it. It runs again only if your audio setup changes."])

    def start(self, now):
        super().start(now)
        self.say("Listen to the clicks first…", "info")

    def click_time(self, index: int) -> float:
        return self.t0 + index * self.spb

    def _schedule(self, now):
        self.t0 = now + 0.8
        self.taps.clear()
        events = [NoteEvent(self.click_time(i), CLICK_HI if i % 4 == 0 else CLICK_LO, 100, 0.05, "drums")
                  for i in range(LEAD_IN + TAPS)]
        self.ctx.backing(events, tag="sync")

    def note_on(self, note, velocity, now):
        if self.t0 is not None and not self.done:
            self.taps.append(now)

    def released(self, now):
        if not self.armed:
            self.armed = True

    def offsets(self) -> list[float]:
        """Each tap's delay after the click it follows. Sound can only arrive
        late, so a tap up to 0.8 of a beat after a click belongs to that click
        (people tap slightly early, hence the small negative margin)."""
        result = []
        for tap in self.taps:
            position = (tap - self.t0) / self.spb
            index = int((position + 0.2) // 1)
            if LEAD_IN <= index < LEAD_IN + TAPS:
                result.append(tap - self.click_time(index))
        return result

    def tick(self, now):
        if self.done:
            return
        if self.t0 is None:
            if self.armed and not self.ctx.held:
                self._schedule(now)
            return
        beat = (now - self.t0) / self.spb
        if beat < LEAD_IN + TAPS:
            self.say(f"Listen to {LEAD_IN} clicks, then tap any key with each click.", "info")
        if beat >= LEAD_IN + TAPS - 1 + 0.9:  # taps may trail the last click by up to 0.8 s
            offsets = self.offsets()
            if len(offsets) >= NEEDED and statistics.pstdev(offsets) <= MAX_SPREAD:
                offset = statistics.median(offsets)
                self.ctx.save_timing_offset(offset)
                latency = self.ctx.store.setting("audio_latency", None) if self.ctx.store is not None else None
                save_sync(self.ctx.store, self.ctx.timing_offset, latency)
                early = "after" if offset >= 0 else "before"
                self.finish(now, 3, 1.0, f"Sound check done: you hear the beat about "
                                        f"{abs(offset) * 1000:.0f} ms {early} it was sent. The screen now matches.",
                            {"offset_ms": round(offset * 1000), "taps": len(offsets)}, graded=False)
                return
            self.tries += 1
            self.t0 = None
            self.armed = False
            if len(offsets) >= NEEDED:
                self.say("Your taps were a bit uneven. Play any key to try again (or S to skip).", "warn")
            else:
                self.say("I didn't catch enough taps. Play any key to try again (or S to skip).", "warn")

    def stop(self):
        super().stop()
        self.ctx.stop_backing("sync")

    def view(self, now) -> View:
        # Nothing here may move in time with the clicks, or the eyes lead the
        # hands and the check measures the screen instead of the sound.
        caption = f"taps: {len(self.taps)}" if self.t0 is not None else ""
        return View(block=self.block, title="Sound check · tap with the clicks", big="♪",
                    caption=caption, lesson="Follow your ears. Closing your eyes is fine.",
                    piano=PianoView(held=frozenset(self.ctx.held)), feedback=self.feedback, tone=self.tone,
                    listening=self.t0 is not None)
