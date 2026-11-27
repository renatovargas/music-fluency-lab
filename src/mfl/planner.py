"""Builds today's lesson from spaced-repetition state. No choices required.

A session has four blocks (about 30 minutes) followed by open-ended free play:
  Warm-up   — due chord reviews, interleaved across keys (recall first)
  Learn     — new skills from the next unit: probe, teach, recall
  Navigate  — progressions: walks, then play-along with fading charts
  Ear       — scale degrees, melodic echo, chords by ear
  Play      — free play with chord naming and optional drums

Each exercise's difficulty follows its history. Progressions move from a
guided walk to play-along with symbols, then Roman numerals, then no chart,
at rising tempos. Lapses step back down. Keys rotate among those the
learner has met, to train transfer rather than memorizing one key.
"""

from __future__ import annotations

from datetime import date
import random

from mfl import srs
from mfl.curriculum import SKILLS, UNITS, Skill, introduced_keys
from mfl.theory import PROGRESSIONS, Key, parse_chord

BLOCKS = ("Warm-up", "Learn", "Navigate", "Ear", "Play")
BUDGET = {"Warm-up": 5.0, "Learn": 9.0, "Navigate": 9.0, "Ear": 7.0}
MAX_NEW = 5
TOTAL = 30.0  # minutes of structured practice before free play


def estimate_minutes(item: dict) -> float:
    kind = item["kind"]
    if kind == "chord":
        return 1.0 if item.get("mode") == "new" else 0.4
    if kind == "walk":
        return 0.6 * len(item.get("loops", [1])) * len(PROGRESSIONS[item["prog"]].romans) / 4 + 0.5
    if kind == "playalong":
        prog = PROGRESSIONS[item["prog"]]
        bars = len(prog.bars) * (item.get("passes", 2) + (1 if item.get("listen") else 0)) + 1
        return bars * 4 * 60 / item.get("bpm", 70) / 60 + 0.4
    if kind in ("degrees", "echo", "chordear"):
        return 0.4 * item.get("rounds", 5) + 0.3
    return 0.0


def new_candidates(states: dict, limit: float) -> list[Skill]:
    """Next unintroduced skills along the path, up to ``limit`` weighted items
    (a chord counts half; chords are quick to probe). Stops at a unit whose
    introduced skills are mostly still shaky, so it gets consolidated first."""
    result: list[Skill] = []
    weight = 0.0
    for unit in UNITS:
        introduced = [states[s.id] for s in unit.skills if (states.get(s.id) or {}).get("reps")]
        for s in unit.skills:
            if not (states.get(s.id) or {}).get("reps"):
                cost = 0.5 if s.kind == "chord" else 1.0
                if weight + cost > limit:
                    return result
                result.append(s)
                weight += cost
        struggling = sum(1 for st in introduced if (st.get("last_grade") or 0) < srs.GOOD)
        if struggling > max(1, len(introduced) // 3):
            break
    return result


def _key_choices(states: dict, skill: Skill) -> list[str]:
    keys = introduced_keys(states)
    return keys or ["C"]


def chord_item(skill: Skill, state: dict | None, rng: random.Random, states: dict, mode: str) -> dict:
    item = {"kind": "chord", "skill": skill.id, "symbol": skill.p["symbol"], "mode": mode}
    # Seasoned chords are sometimes asked by function, to tie chords to keys.
    if mode == "review" and state and float(state.get("interval", 0)) >= 4 and rng.random() < 0.5:
        chord = parse_chord(skill.p["symbol"])
        options = []
        for key_text in introduced_keys(states):
            key = Key.parse(key_text)
            analysis = key.analyze(chord)
            if analysis and "/" not in analysis and chord.pcs <= set(key.scale.pcs):
                options.append((key_text, analysis))
        if options:
            key_text, roman = rng.choice(options)
            item.update(key=key_text, roman=roman)
    return item


def prog_item(skill: Skill, state: dict | None, rng: random.Random, states: dict, mode: str) -> dict:
    p = skill.p
    base = {"skill": skill.id, "prog": p["prog"], "key": p["key"], "mode": mode}
    if mode == "new":
        return {**base, "kind": "walk", "loops": ["full", "symbols"], "demo": True}
    reps = int(state.get("reps", 1)) if state else 1
    stage = min(reps, 5)
    if state and (state.get("last_grade") or 3) <= srs.HARD:
        stage = max(1, stage - 1)
    if stage == 1:
        return {**base, "kind": "walk", "loops": ["symbols", "roman"]}
    grooves = [SKILLS[s].p["pattern"] for s in states if s.startswith("groove/") and states[s].get("reps")]
    if stage == 2:
        return {**base, "kind": "playalong", "pattern": "whole", "bpm": 66, "cue": "symbols", "passes": 2}
    if stage == 3:
        return {**base, "kind": "playalong", "pattern": "halves", "bpm": 72, "cue": "roman", "passes": 2}
    pattern = rng.choice(grooves) if grooves else "quarters"
    if pattern == "waltz":
        pattern = "halves"
    bpm = 76 + 4 * (stage - 4) + rng.choice((0, 4, 8))
    return {**base, "kind": "playalong", "pattern": pattern, "bpm": bpm, "cue": "roman" if stage == 4 else "none",
            "passes": 2}


def groove_item(skill: Skill, state: dict | None, rng: random.Random, states: dict, mode: str) -> dict:
    pattern = skill.p["pattern"]
    progs = [SKILLS[s] for s in states if s.startswith("prog/") and states[s].get("reps")]
    candidates = [s for s in progs if PROGRESSIONS[s.p["prog"]].mode == "major" and len(PROGRESSIONS[s.p["prog"]].bars) == 4]
    host = rng.choice(candidates) if candidates else SKILLS["prog/axis/C"]
    reps = int(state.get("reps", 0)) if state else 0
    item = {"kind": "playalong", "skill": skill.id, "prog": host.p["prog"], "key": host.p["key"], "mode": mode,
            "pattern": pattern, "passes": 2}
    if mode == "new":
        item.update(bpm=64 if pattern != "pop8" else 60, cue="full", listen=True)
    else:
        item.update(bpm=min(100, 68 + 5 * reps), cue="symbols" if reps < 3 else "roman")
    return item


def ear_item(skill: Skill, state: dict | None, rng: random.Random, states: dict, mode: str) -> dict:
    keys = _key_choices(states, skill)
    key = rng.choice(keys) if mode == "review" else keys[0]
    item = {"kind": skill.kind, "skill": skill.id, "key": key, "mode": mode,
            "rounds": 5 if mode == "new" else 6}
    item.update({k: v for k, v in skill.params})
    if skill.kind == "echo":
        item["rounds"] = 4
    return item


BUILDERS = {"chord": chord_item, "prog": prog_item, "groove": groove_item, "degrees": ear_item, "echo": ear_item,
            "chordear": ear_item}
BLOCK_OF = {"chord": "Warm-up", "prog": "Navigate", "groove": "Navigate", "degrees": "Ear", "echo": "Ear",
            "chordear": "Ear"}


def plan_session(states: dict[str, dict], today: date, minutes: float = 30.0, seed: int | None = None) -> list[dict]:
    """Return an ordered list of plan items for today."""
    rng = random.Random(seed if seed is not None else today.toordinal())
    scale = minutes / 30.0
    due = [(srs.overdue_ratio(st, today), sid) for sid, st in states.items()
           if sid in SKILLS and st.get("reps") and srs.is_due(st, today)]
    due.sort(reverse=True)
    blocks: dict[str, list[dict]] = {b: [] for b in BLOCKS}
    spent = {b: 0.0 for b in BLOCKS}

    budget = {b: v * scale for b, v in BUDGET.items()}

    def add(block: str, item: dict, force: bool = False) -> bool:
        cost = estimate_minutes(item)
        if not force and spent[block] + cost > budget[block] and blocks[block]:
            return False
        item["block"] = block
        blocks[block].append(item)
        spent[block] += cost
        return True

    # Reviews, most overdue first, in their natural blocks.
    for _, sid in due:
        skill = SKILLS[sid]
        item = BUILDERS[skill.kind](skill, states.get(sid), rng, states, "review")
        add(BLOCK_OF[skill.kind], item)
    # Interleave the warm-up so similar chords don't come back to back.
    rng.shuffle(blocks["Warm-up"])

    # New material, limited when many reviews are waiting. Learning may use
    # the time that reviews leave free.
    max_new = MAX_NEW if len(due) <= 12 else 2
    review_time = sum(spent.values())
    budget["Learn"] = max(budget["Learn"], min(16.0 * scale, TOTAL * scale - review_time - 4.0 * scale))
    for skill in new_candidates(states, max_new):
        item = BUILDERS[skill.kind](skill, states.get(skill.id), rng, states, "new")
        if not add("Learn", item):
            break

    # Consolidate today's new progressions by playing them with the band
    # (ungraded, so the same-day repetition does not inflate the interval).
    for item in [i for i in blocks["Learn"] if i["kind"] == "walk"][:2]:
        add("Navigate", {"kind": "playalong", "skill": item["skill"], "prog": item["prog"], "key": item["key"],
                         "mode": "practice", "graded": False, "pattern": "halves", "bpm": 66, "cue": "symbols",
                         "passes": 2, "listen": True})

    # Always some ear training once any ear skill has been introduced.
    if not blocks["Ear"]:
        ear = [SKILLS[s] for s, st in states.items() if s in SKILLS and SKILLS[s].kind in ("degrees", "echo",
               "chordear") and st.get("reps")]
        if ear:
            weakest = min(ear, key=lambda s: srs.retention(states[s.id], today))
            add("Ear", ear_item(weakest, states[weakest.id], rng, states, "review"))
    # And some navigation once any progression is known.
    if not blocks["Navigate"]:
        progs = [SKILLS[s] for s, st in states.items() if s in SKILLS and SKILLS[s].kind == "prog" and st.get("reps")]
        if progs:
            weakest = min(progs, key=lambda s: srs.retention(states[s.id], today))
            add("Navigate", prog_item(weakest, states[weakest.id], rng, states, "review"))

    plan: list[dict] = []
    for block in BLOCKS[:-1]:
        plan.extend(blocks[block])
    plan.append({"kind": "free", "skill": "free", "block": "Play", "mode": "free"})
    return plan


def describe(item: dict) -> str:
    """One line for the plan overview."""
    skill = SKILLS.get(item.get("skill", ""))
    kind = item["kind"]
    if kind == "free":
        return "Free play: a song you love"
    title = skill.title if skill else item.get("skill", kind)
    tag = "new" if item.get("mode") == "new" else "with the band" if item.get("mode") == "practice" else ""
    if kind == "playalong":
        title += f" · {item.get('bpm')} BPM"
    return f"{title}{' · ' + tag if tag else ''}"
