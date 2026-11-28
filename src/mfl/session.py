"""The practice session: today's plan, run one exercise after another.

UI-agnostic. A front end feeds MIDI events and clock ticks, calls hint/skip/
back/repeat, and renders ``view()``. Each new kind of exercise opens with an
intro card that says, in plain words, what to do; the learner starts it by
playing any key, so nothing begins before they are ready. The session records results, updates spaced-
repetition state, saves its position for resume, and re-queues an item later
in the session when it went badly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import random
import time

from mfl import srs
from mfl.exercises import Context, Exercise, Result, View, build
from mfl.planner import BLOCKS, describe, estimate_minutes, plan_session
from mfl.storage import Progress

TRANSITION = 3.0  # seconds to show "exercise complete" before moving on
IDLE = 90.0  # seconds without input after which practice time stops counting


@dataclass
class SessionView:
    view: View
    blocks: list[tuple[str, str]] = field(default_factory=list)  # (name, done|current|todo)
    position: int = 0
    total: int = 0
    minutes: float = 0.0
    planned_minutes: float = 0.0
    streak: int = 0
    state: str = "welcome"
    next_up: str = ""


def streak(days: list[str], today: date) -> int:
    """Consecutive practice days, allowing up to two rest days between them."""
    seen = sorted({date.fromisoformat(d) for d in days if d}, reverse=True)
    if not seen or (today - seen[0]).days > 3:
        return 0
    count, previous = 1, seen[0]
    for d in seen[1:]:
        if (previous - d).days > 3:
            break
        count += 1
        previous = d
    return count


class Practice:
    def __init__(self, store: Progress, audio, *, today: date | None = None, minutes: float = 30.0,
                 seed: int | None = None, low: int = 53, high: int = 77, clock=time.perf_counter):
        self.store = store
        self.audio = audio
        self.today = today or date.today()
        self.clock = clock
        day = self.today.isoformat()
        rng = random.Random(seed if seed is not None else self.today.toordinal() * 31 + store.sessions_on(day))
        self.ctx = Context(audio, store, rng, low, high)
        existing = store.open_session(day)
        if existing is not None:
            self.session_id = existing["id"]
            self.plan: list[dict] = existing["plan"]
            self.position = min(existing["position"], len(self.plan) - 1)
            self.resumed = self.position > 0
        else:
            self.plan = plan_session(store.skills(), self.today, minutes, seed)
            self.session_id = store.create_session(day, self.plan)
            self.position = 0
            self.resumed = False
        self._ensure_sync()
        self.state = "welcome"
        self.exercise: Exercise | None = None
        self.last_view: View | None = None
        self.last_result: Result | None = None
        self.result_at = 0.0
        self.requeued: set[str] = set()
        self.active_seconds = 0.0
        self.saved_seconds = 0.0
        self.last_activity = clock()
        self.last_tick = clock()
        self.streak = streak(store.practice_days(), self.today)
        self.completed_now = False
        self.last_run: tuple[str, bool] | None = None  # (kind, new) of the last exercise started
        self.finished_position: int | None = None

    def sync_needed(self) -> bool:
        """True until a sound check has been done with the current audio buffer."""
        from mfl.exercises.sync import VERSION

        sync = self.store.setting("sync")
        return (not isinstance(sync, dict) or sync.get("version") != VERSION
                or sync.get("latency") != self.store.setting("audio_latency", None))

    def _ensure_sync(self):
        """Put a short sound check before the first band exercise when needed."""
        rest = self.plan[self.position:]
        if not self.sync_needed() or any(i["kind"] == "sync" for i in rest):
            return
        for index, item in enumerate(rest, self.position):
            if item["kind"] == "playalong":
                self.plan.insert(index, {"kind": "sync", "skill": "sync", "block": item.get("block", "Navigate"),
                                         "mode": "practice", "graded": False})
                self.store.update_session(self.session_id, plan=self.plan)
                return

    # ---- plan helpers ---------------------------------------------------------------
    @property
    def item(self) -> dict:
        return self.plan[self.position]

    def planned_minutes(self) -> float:
        return sum(estimate_minutes(i) for i in self.plan)

    def block_states(self) -> list[tuple[str, str]]:
        current = self.item.get("block") if self.state != "welcome" else None
        remaining = {i.get("block") for i in self.plan[self.position:]}
        result = []
        for b in BLOCKS:
            if not any(i.get("block") == b for i in self.plan):
                continue
            state = "current" if b == current else "todo" if b in remaining else "done"
            result.append((b, state))
        return result

    # ---- input --------------------------------------------------------------------------
    def on_midi(self, kind: str, note: int, velocity: int, now: float | None = None):
        now = self.clock() if now is None else now
        if kind == "pedal":
            self.audio.pedal(velocity >= 64)
            return
        if kind == "pad":
            self.audio.note_on(note, velocity, source="pads", instrument="drums")
            return
        self.last_activity = now
        if kind == "on":
            self.audio.note_on(note, velocity)
            if note in self.ctx.held:
                return
            self.ctx.held.add(note)
            self.ctx.last_note_on = now
            self.ctx.learner_note_on(now)
            if self.state == "exercise" and self.exercise is not None:
                self.exercise.note_on(note, velocity, now)
        else:
            self.audio.note_off(note)
            if note not in self.ctx.held:
                return
            self.ctx.held.discard(note)
            if self.state == "exercise" and self.exercise is not None:
                self.exercise.note_off(note, now)
            if not self.ctx.held:
                self.ctx.last_release = now
                if self.state == "welcome":
                    self.begin(now)
                elif self.state == "intro":
                    self._start_current(now)
                elif self.state == "exercise" and self.exercise is not None:
                    self.exercise.released(now)
        self._check_done(now)

    def tick(self, now: float | None = None):
        now = self.clock() if now is None else now
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now
        if now - self.last_activity < IDLE and self.state != "welcome":
            self.active_seconds += min(dt, 1.0)
        self.ctx.update(now)
        if self.state == "exercise" and self.exercise is not None:
            self.exercise.tick(now)
            self._check_done(now)
        elif self.state == "between":
            if now - self.result_at >= TRANSITION and not self.ctx.held:
                self._prepare(now)

    def hint(self, now: float | None = None):
        now = self.clock() if now is None else now
        if self.state == "exercise" and self.exercise is not None:
            self.exercise.hint(now)

    def skip(self, now: float | None = None):
        now = self.clock() if now is None else now
        if self.state == "welcome":
            self.begin(now)
            return
        if self.state not in ("exercise", "intro") or self.exercise is None or self.exercise.kind == "free":
            return
        self.exercise.stop()
        self.store.add_result(skill=self.exercise.skill_id, kind=f"{self.exercise.kind}_skip", grade=0, score=None,
                              seconds=now - self.exercise.started, hints=self.exercise.hints,
                              session=self.session_id, day=self.today.isoformat())
        self.last_result = None
        self._advance(now)

    def restart_exercise(self, now: float | None = None):
        """Start the current exercise again, or repeat the one just finished."""
        now = self.clock() if now is None else now
        if self.state in ("exercise", "intro"):
            self._start_current(now)
        elif self.state == "between" and self.finished_position is not None:
            self._goto(self.finished_position, now, intro=False)

    def back(self, now: float | None = None):
        """Go back one step and show its explanation again."""
        now = self.clock() if now is None else now
        if self.state == "welcome":
            return
        if self.state == "between" and self.finished_position is not None:
            target = self.finished_position
        else:
            target = max(0, self.position - 1)
        self._goto(target, now, intro=True)

    def change_tempo(self, delta: float, now: float | None = None) -> float:
        """Make play-alongs slower or faster (a scale on written tempos). A
        running play-along starts again at the new tempo."""
        now = self.clock() if now is None else now
        scale = self.ctx.set_tempo_scale(self.ctx.tempo_scale + delta)
        ex = self.exercise
        if ex is not None and ex.kind == "playalong":
            if self.state == "intro":
                self.exercise = build(self.item, self.ctx)
            elif self.state == "exercise":
                self._start_current(now)
        return scale

    def nudge_timing(self, delta: float) -> float:
        """Shift the play-along lane (and timing judgement) by hand: positive
        draws it later, for when the cursor reaches a beat before you hear it."""
        from mfl.exercises.sync import save_sync

        self.ctx.save_timing_offset(self.ctx.timing_offset + delta)
        sync = self.store.setting("sync")
        latency = sync.get("latency") if isinstance(sync, dict) else self.store.setting("audio_latency", None)
        save_sync(self.store, self.ctx.timing_offset, latency)
        return self.ctx.timing_offset

    def _goto(self, position: int, now: float, intro: bool):
        if self.exercise is not None:
            self.exercise.stop()
        self.position = min(max(0, position), len(self.plan) - 1)
        self.store.update_session(self.session_id, position=self.position, add_seconds=self._unsaved_seconds())
        self.last_result = None
        if intro:
            self._prepare(now, force_intro=True)
        else:
            self._start_current(now)

    # ---- flow ----------------------------------------------------------------------------
    def begin(self, now: float):
        if self.state == "welcome":
            self._prepare(now)

    def needs_intro(self) -> bool:
        item = self.item
        if item["kind"] == "free":
            return False
        return self.last_run != (item["kind"], item.get("mode") == "new")

    def _prepare(self, now: float, force_intro: bool = False):
        """Show the next exercise's intro card when it is a new kind of task,
        otherwise start it straight away."""
        if force_intro or self.needs_intro():
            if self.exercise is not None:
                self.exercise.stop()
            self.exercise = build(self.item, self.ctx)
            self.state = "intro"
        else:
            self._start_current(now)

    def _start_current(self, now: float):
        if self.exercise is not None:
            self.exercise.stop()
        self.exercise = build(self.item, self.ctx)
        self.exercise.start(now)
        self.state = "exercise"
        self.last_run = (self.item["kind"], self.item.get("mode") == "new")
        if self.exercise.kind == "free" and not self.completed_now:
            self.completed_now = True
            self.store.update_session(self.session_id, position=self.position, finished=True,
                                      add_seconds=self._unsaved_seconds())

    def _check_done(self, now: float):
        ex = self.exercise
        if self.state != "exercise" or ex is None or not ex.done or ex.result is None:
            return
        result = ex.result
        self.last_view = ex.view(now)
        ex.stop()
        if ex.kind == "free":
            return
        self.store.add_result(skill=result.skill, kind=result.kind, grade=result.grade, score=result.score,
                              seconds=result.seconds, hints=result.hints,
                              details={**result.details, "summary": result.summary},
                              session=self.session_id, day=self.today.isoformat())
        if result.graded and result.skill in self._skill_ids():
            state = srs.review(self.store.skill(result.skill), result.skill, result.grade, self.today)
            self.store.save_skill(state)
        if result.graded and result.grade == srs.AGAIN and result.skill not in self.requeued:
            # Come back to it a little later today, as a review.
            self.requeued.add(result.skill)
            retry = dict(self.item, mode="review")
            insert_at = min(len(self.plan) - 1, self.position + 3)
            self.plan.insert(insert_at, retry)
        self.last_result = result
        self.result_at = now
        self.finished_position = self.position
        self._advance(now, show_result=True)

    def _skill_ids(self):
        from mfl.curriculum import SKILLS
        return SKILLS

    def _advance(self, now: float, show_result: bool = False):
        if self.position < len(self.plan) - 1:
            self.position += 1
        self.store.update_session(self.session_id, position=self.position, plan=self.plan,
                                  add_seconds=self._unsaved_seconds())
        if show_result:
            self.state = "between"
            self.exercise = None
        else:
            self._prepare(now)

    def _unsaved_seconds(self) -> float:
        delta = self.active_seconds - self.saved_seconds
        self.saved_seconds = self.active_seconds
        return delta

    def close(self):
        if self.exercise is not None:
            self.exercise.stop()
        self.store.update_session(self.session_id, add_seconds=self._unsaved_seconds())

    # ---- view ------------------------------------------------------------------------------
    def welcome_view(self) -> View:
        hour = time.localtime().tm_hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        lines = []
        for block in BLOCKS:
            items = [describe(i) for i in self.plan[self.position:] if i.get("block") == block]
            if not items:
                continue
            shown = "; ".join(items[:3]) + (f" (+{len(items) - 3} more)" if len(items) > 3 else "")
            lines.append(f"{block:<9} {shown}")
        if self.resumed:
            title = f"{greeting}. Welcome back. Let's pick up where you left off."
        elif self.streak > 1:
            title = f"{greeting}. Day {self.streak} of your streak."
        else:
            title = f"{greeting}. Here's today's practice."
        return View(block="Today", title=title, big="MFL", caption="Musical Fluency Lab",
                    lesson="\n".join(lines), feedback="Play any key to begin.", tone="good")

    def intro_view(self) -> View:
        heading, why, steps = self.exercise.intro()
        lesson = heading + ("\n" + why if why else "") + "\n\n" + "\n".join(
            f"{i}. {step}" for i, step in enumerate(steps, 1))
        if self.last_result is not None:
            lesson = f"Last: {self.last_result.summary}\n\n" + lesson
        return View(block=self.item.get("block", ""), title="What's next", lesson=lesson,
                    feedback="When you're ready, play any key to start.  (B goes back, S skips)", tone="good")

    def view(self, now: float | None = None) -> SessionView:
        now = self.clock() if now is None else now
        next_up = ""
        if self.state == "welcome":
            view = self.welcome_view()
        elif self.state == "intro" and self.exercise is not None:
            view = self.intro_view()
        elif self.state == "between" and self.last_view is not None:
            # A screen of its own, so the end of an exercise is unmistakable
            # (reusing the exercise's screen looked as if it were still going).
            result = self.last_result
            done = self.last_view
            view = View(block=done.block, title="Exercise complete", big="★", big_tone="good",
                        caption=done.title,
                        lesson=f"Next: {describe(self.item)}. I'll explain it before it starts. "
                               "Nothing to play right now.")
            if result is not None:
                good = result.grade >= srs.GOOD
                view.feedback = (f"{'✓' if good else '↻ Coming back later today ·'} {result.summary}"
                                 "   (R: do it again)")
                view.tone = "good" if good else "warn"
        elif self.exercise is not None:
            view = self.exercise.view(now)
            if self.exercise.kind == "free" and self.completed_now and now - self.exercise.started < 6:
                view.feedback = "Session complete and saved. Enjoy playing. Press Q when you're done."
                view.tone = "good"
        else:
            view = View()
        return SessionView(view=view, blocks=self.block_states(), position=self.position, total=len(self.plan),
                           minutes=self.active_seconds / 60, planned_minutes=self.planned_minutes(),
                           streak=self.streak, state=self.state, next_up=next_up)


def week_start(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()
