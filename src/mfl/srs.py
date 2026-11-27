"""Spaced repetition: an SM-2 style scheduler with four grades.

Grades: 1 = needed help (again), 2 = hard, 3 = good, 4 = easy.
Intervals are in days. Practice happens about five days a week, so items
falling due on a skipped day simply wait. The planner reviews the most
overdue items first.
"""

from __future__ import annotations

from datetime import date, timedelta
import math

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
GRADE_WORDS = {AGAIN: "needed help", HARD: "hard", GOOD: "good", EASY: "easy"}
MAX_INTERVAL = 120.0


def new_state(skill: str) -> dict:
    return {"skill": skill, "reps": 0, "lapses": 0, "ease": 2.5, "interval": 0.0, "due": None,
            "last_review": None, "last_grade": None, "introduced": None}


def review(state: dict | None, skill: str, grade: int, today: date) -> dict:
    """Return the new state after a graded review."""
    s = dict(state) if state else new_state(skill)
    grade = max(AGAIN, min(EASY, int(grade)))
    ease, interval, reps = float(s["ease"]), float(s["interval"]), int(s["reps"])
    if reps == 0:
        interval = {AGAIN: 1.0, HARD: 1.0, GOOD: 2.0, EASY: 4.0}[grade]
        ease += {AGAIN: -0.2, HARD: -0.1, GOOD: 0.0, EASY: 0.1}[grade]
    else:
        # Credit time actually survived when a review was late but successful.
        if s.get("last_review") and grade >= GOOD:
            elapsed = (today - date.fromisoformat(s["last_review"])).days
            interval = max(interval, min(elapsed, interval * 2))
        if grade == AGAIN:
            s["lapses"] = int(s["lapses"]) + 1
            ease -= 0.2
            interval = 1.0
        elif grade == HARD:
            ease -= 0.15
            interval = max(1.0, interval * 1.2)
        elif grade == GOOD:
            interval = max(interval + 1, interval * ease)
        else:
            ease += 0.15
            interval = max(interval + 2, interval * ease * 1.3)
    s["ease"] = round(max(1.3, min(3.0, ease)), 3)
    s["interval"] = round(min(MAX_INTERVAL, interval), 2)
    s["reps"] = reps + 1
    s["due"] = (today + timedelta(days=max(1, round(s["interval"])))).isoformat()
    s["last_review"] = today.isoformat()
    s["last_grade"] = grade
    s["introduced"] = s.get("introduced") or today.isoformat()
    return s


def is_due(state: dict, today: date) -> bool:
    return bool(state.get("due")) and date.fromisoformat(state["due"]) <= today


def overdue_ratio(state: dict, today: date) -> float:
    """How late a review is relative to its interval (higher = more urgent)."""
    if not state.get("due"):
        return 0.0
    late = (today - date.fromisoformat(state["due"])).days
    return (late + 1) / max(1.0, float(state["interval"]))


def retention(state: dict, today: date) -> float:
    """Estimated probability of recall now (exponential forgetting curve
    calibrated so recall is ~90% when an item falls due)."""
    if not state or not state.get("last_review"):
        return 0.0
    elapsed = (today - date.fromisoformat(state["last_review"])).days
    interval = max(0.5, float(state["interval"]))
    return math.exp(math.log(0.9) * elapsed / interval)


def strength(state: dict | None) -> float:
    """0–1 mastery for display: three weeks of stable interval counts as solid."""
    if not state or not state.get("reps"):
        return 0.0
    return max(0.05, min(1.0, float(state["interval"]) / 21.0))
