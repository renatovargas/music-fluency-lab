"""Progress report shared by the in-app progress screen and ``mfl stats``."""

from __future__ import annotations

from datetime import date, timedelta
import json

from rich.text import Text

from mfl import srs
from mfl.curriculum import SKILLS, UNITS
from mfl.session import streak, week_start
from mfl.storage import Progress
from mfl.theory import CIRCLE_OF_FIFTHS, Key


def _bar(fraction: float, width: int = 12) -> Text:
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    color = "#3fbf6a" if fraction >= 0.66 else "#e0b84a" if fraction >= 0.33 else "#5b8def"
    return Text("█" * filled, color) + Text("░" * (width - filled), "#44445a")


def key_strength(states: dict, key: Key) -> float | None:
    """Average strength of the key's diatonic triads that have been met."""
    values = []
    for _, chord in key.diatonic():
        if chord.quality.suffix == "dim":
            continue
        state = states.get(f"chord/{chord.ascii}")
        if state and state.get("reps"):
            values.append(srs.strength(state))
    prog_states = [s for sid, s in states.items() if sid.startswith("prog/") and sid.endswith(f"/{key.ascii}")]
    values += [srs.strength(s) for s in prog_states if s.get("reps")]
    return sum(values) / len(values) if values else None


def report(store: Progress, today: date | None = None) -> Text:
    today = today or date.today()
    states = store.skills()
    out = Text()
    days = store.practice_days()
    due_today = sum(1 for s in states.values() if s.get("reps") and srs.is_due(s, today))
    due_tomorrow = sum(1 for s in states.values() if s.get("reps") and srs.is_due(s, today + timedelta(days=1)))
    introduced = sum(1 for sid, s in states.items() if sid in SKILLS and s.get("reps"))
    out.append("Your progress\n", "bold")
    out.append(f"Streak {streak(days, today)} · practice days {len(days)} · sessions {store.completed_sessions()} · "
               f"this week {store.minutes_since(week_start(today)):.0f} min\n", "dim")
    out.append(f"Skills met {introduced}/{len(SKILLS)} · due today {due_today} · due by tomorrow {due_tomorrow}\n\n",
               "dim")

    out.append("Keys around the circle of fifths (major / relative minor)\n", "bold")
    for row in range(2):
        for tonic in CIRCLE_OF_FIFTHS:
            k = Key.parse(tonic) if row == 0 else Key.parse(tonic).relative
            value = key_strength(states, k)
            label = f" {k.short:<4}"
            if value is None:
                out.append(label, "#55556a")
            else:
                color = "#3fbf6a" if value >= 0.66 else "#e0b84a" if value >= 0.33 else "#5b8def"
                out.append(label, f"bold {color}")
        out.append("\n")
    out.append("\n")

    out.append("Path\n", "bold")
    shown = 0
    for unit in UNITS:
        met = [states.get(s.id) for s in unit.skills if (states.get(s.id) or {}).get("reps")]
        if not met and shown >= 2:
            continue
        if not met:
            shown += 1
        strength = sum(srs.strength(s) for s in met) / len(unit.skills)
        mark = "✓" if len(met) == len(unit.skills) and strength >= 0.5 else "◐" if met else "○"
        out.append(f" {mark} ", "bold")
        out.append(f"{unit.title:<42}"[:42])
        out.append(" ")
        out.append(_bar(strength))
        out.append(f" {len(met)}/{len(unit.skills)}\n", "dim")
    out.append("\nRecent\n", "bold")
    for row in store.recent_results(8):
        skill = SKILLS.get(row["skill"])
        title = skill.title if skill else row["skill"]
        try:
            summary = json.loads(row["details"] or "{}").get("summary", "")
        except ValueError:
            summary = ""
        if row["kind"].endswith("_skip"):
            word, color = "skipped", "dim"
        else:
            word = srs.GRADE_WORDS.get(row["grade"], "")
            color = "#3fbf6a" if row["grade"] >= srs.GOOD else "#e0b84a"
        out.append(f" {row['day']}  ", "dim")
        out.append(f"{word:<11}", color)
        out.append(f" {title}")
        if summary:
            out.append(f"  {summary}", "dim")
        out.append("\n")
    return out
