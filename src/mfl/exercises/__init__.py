"""Exercise types and a factory that builds them from plan items."""

from mfl.exercises.base import Context, Exercise, Result, View
from mfl.exercises.chord import ChordExercise
from mfl.exercises.ear import ChordEarExercise, DegreeExercise, EchoExercise
from mfl.exercises.freeplay import FreePlay
from mfl.exercises.progression import PlayAlongExercise, WalkExercise
from mfl.exercises.sync import SyncExercise

KINDS = {
    "chord": ChordExercise,
    "walk": WalkExercise,
    "playalong": PlayAlongExercise,
    "degrees": DegreeExercise,
    "echo": EchoExercise,
    "chordear": ChordEarExercise,
    "free": FreePlay,
    "sync": SyncExercise,
}


def build(item: dict, ctx: Context) -> Exercise:
    exercise = KINDS[item["kind"]](item, ctx)
    if item.get("block"):
        exercise.block = item["block"]
    return exercise


__all__ = ["KINDS", "Context", "Exercise", "Result", "View", "build"]
