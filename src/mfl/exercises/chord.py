"""Single chord. A new chord is taught first: listen, copy the highlighted
keys, then play it from memory. A review asks for it from memory, and two
misses bring the guide back. Nothing advances on a timer: the learner's
playing moves every step."""

from __future__ import annotations

from mfl import srs
from mfl.exercises.base import Exercise, PianoView, View, chord_events
from mfl.theory import Key, comfortable_voicing, identify, parse_chord


def chord_lesson(chord) -> str:
    parts = []
    for note, interval in zip(chord.notes, chord.quality.intervals):
        label = "root" if interval.semitones == 0 else interval.name
        parts.append(f"{note.text} ({label})")
    text = " · ".join(parts)
    suffix = chord.quality.suffix
    if suffix == "":
        third = chord.notes[1]
        text += f"\nLower {third.text} by a half step and it becomes {chord.root.text} minor."
    elif suffix == "m":
        third = chord.notes[1]
        text += f"\nRaise {third.text} by a half step and it becomes {chord.root.text} major."
    elif suffix == "7":
        text += "\nA major triad plus a minor seventh. The tritone inside wants to resolve."
    elif suffix == "maj7":
        text += "\nA major triad plus the note a half step below the root. Soft and open."
    elif suffix == "m7":
        text += "\nA minor triad plus a minor seventh. Mellow, the sound of ii and vi in ballads."
    elif suffix in ("sus4", "sus2"):
        text += "\nNo third. Suspended, so the ear waits for it to resolve."
    if chord.bass is not None:
        text += f"\nPut {chord.bass.text} at the bottom. The bass note defines the sound."
    return text


# Keys in the order they are most useful to mention (familiar ones first).
CONTEXT_KEYS = ("C", "G", "Am", "F", "Em", "D", "Dm", "A", "Bb", "E", "Bm", "Eb", "Gm", "Cm")


def chord_why(chord) -> str:
    """Where this chord lives: its job in the keys that contain it."""
    from mfl.theory import harmonic_function

    roles = []
    for text in CONTEXT_KEYS:
        key = Key.parse(text)
        if not chord.pcs <= set(key.scale.pcs):
            continue
        roman = key.analyze(chord)
        # Skip ♭/♯ numerals (pop convention in minor keys): confusing as context.
        if roman and "/" not in roman and "♭" not in roman and "♯" not in roman:
            job = harmonic_function(roman, key.mode).split(":")[0].split("(")[0].strip()
            roles.append(f"{roman} in {key.name} ({job})")
        if len(roles) == 3:
            break
    sound = {"": "Major chords sound bright and settled.",
             "m": "Minor chords sound darker and more tender.",
             "7": "A dominant seventh is tense: it wants to move to the chord a fifth below.",
             "maj7": "A major seventh sounds soft and open, the colour of many ballads.",
             "m7": "A minor seventh sounds mellow and smooth.",
             "sus4": "A suspended chord sounds unresolved: the ear waits for the third.",
             "sus2": "A suspended chord sounds open and unresolved."}.get(chord.quality.suffix, "")
    where = f"{chord.symbol} is " + ", ".join(roles) + "." if roles else ""
    return " ".join(part for part in (where, sound) if part)


class ChordExercise(Exercise):
    kind = "chord"
    block = "Warm-up"

    def __init__(self, item, ctx):
        super().__init__(item, ctx)
        self.chord = parse_chord(item["symbol"])
        self.voicing = comfortable_voicing(self.chord, ctx.low, ctx.high)
        self.prompt_key = Key.parse(item["key"]) if item.get("key") else None
        self.roman = item.get("roman")
        self.phase = "guided" if self.mode == "new" else "recall"
        self.block = "Learn" if self.mode == "new" else "Warm-up"
        self.accepted = False
        self.blocked = bool(ctx.held)
        self.attempt: set[int] = set()
        self.misses = 0
        self.guided_used = False
        self.shift: int | None = None
        self.first_try = True
        self.attempt_start = 0.0
        self.recall_time = 0.0

    # ---- helpers ------------------------------------------------------------------------
    @property
    def target(self) -> frozenset:
        shift = self._best_shift(self.ctx.held) if self.ctx.held else (self.shift or 0)
        return frozenset(n + shift for n in self.voicing)

    def _best_shift(self, held) -> int:
        """The octave of the guide shape that best overlaps the held keys, so the
        shape may be played in any octave and a left-hand bass can be added."""
        best, best_key = 0, (-1, 0)
        for shift in range(-36, 37, 12):
            if not all(0 <= n + shift <= 127 for n in self.voicing):
                continue
            key = (len({n + shift for n in self.voicing} & held), -abs(shift))
            if key > best_key:
                best, best_key = shift, key
        return best

    def _demo(self, now):
        events = chord_events(self.voicing, 0.0, 0.55, 76, roll=0.11) + chord_events(self.voicing, 0.7, 1.1, 82)
        self.ctx.demo(events, now)

    def _guide(self, now, message):
        self.phase = "guided"
        self.guided_used = True
        self.shift = None
        self.say(message, "info")
        self._demo(now)

    def start(self, now):
        super().start(now)
        self.attempt_start = now
        if self.phase == "guided":
            self._guide(now, f"Listen to {self.chord.symbol}, then press the highlighted keys together.")
        else:
            self.say(f"Play {self._asked()} from memory. Any order or octave is fine.", "info")

    def _asked(self) -> str:
        if self.roman and self.prompt_key:
            return f"{self.roman} in {self.prompt_key.name}"
        return self.chord.symbol

    # ---- MIDI -----------------------------------------------------------------------------
    def note_on(self, note, velocity, now):
        if self.blocked or self.accepted:
            return
        if not self.attempt:
            self.attempt_start = now
        self.attempt.add(note)
        held = self.ctx.held
        if self.phase == "guided":
            self.shift = self._best_shift(held)
            target = self.target
            correct = target <= held and all(
                n in target or (n < min(target) and n % 12 in self.chord.pcs) for n in held)
        else:
            correct = self.chord.matches(held)
        if correct:
            self.accepted = True
            elapsed = now - self.attempt_start
            if self.phase == "recall":
                self.recall_time = elapsed
                self.say(f"✓ {self.chord.name}: {self.chord.spelled}", "good")
            else:
                self.say("✓ That's it. Now let go of the keys.", "good")

    def released(self, now):
        if self.blocked:
            self.blocked = False
            self.attempt.clear()
            return
        if self.accepted:
            if self.phase == "recall":
                self._complete(now)
                return
            self.phase = "recall"
            self.accepted = False
            self.attempt.clear()
            self.say(f"Now the guide is hidden. Play {self.chord.symbol} again from memory.", "info")
            return
        if len(self.attempt) >= 2:
            played = identify(self.attempt)
            name = played[0].symbol if played else "that"
            self.first_try = False
            if self.phase == "recall":
                self.misses += 1
                hint = self._difference(self.attempt)
                if self.misses >= 2:
                    self._guide(now, f"You played {name}. Let's look at it together: copy the highlighted keys.")
                else:
                    self.say(f"You played {name}. {hint}Try again (H shows it).", "warn")
            else:
                self.say(f"You played {name}. Press only the highlighted keys, all together.", "warn")
        self.attempt.clear()

    def _difference(self, notes) -> str:
        missing = [n.text for n in self.chord.notes if n.pc not in {x % 12 for x in notes}]
        if missing and len(missing) <= 2:
            return f"Missing: {', '.join(missing)}. "
        return ""

    def hint(self, now):
        if self.accepted:
            return
        self.hints += 1
        if self.phase == "guided":
            self._demo(now)
        else:
            self._guide(now, "Here's the shape. Copy the highlighted keys, then play it from memory.")

    def _complete(self, now):
        if self.mode == "new":
            grade = srs.GOOD if self.misses == 0 and self.hints == 0 else srs.HARD
        elif self.guided_used:
            grade = srs.AGAIN
        elif self.misses:
            grade = srs.HARD
        else:
            grade = srs.EASY if self.recall_time < 2.5 else srs.GOOD
        summary = f"{self.chord.symbol} {srs.GRADE_WORDS[grade]}"
        if self.recall_time:
            summary += f" · found in {self.recall_time:.1f} s"
        self.finish(now, grade, 1.0 if grade >= srs.GOOD else 0.5, summary,
                    {"misses": self.misses, "guided": self.guided_used, "time": round(self.recall_time, 2)})

    def intro(self):
        if self.mode == "new":
            return (f"Learn a new chord: {self.chord.symbol} ({self.chord.name})", chord_why(self.chord), [
                "Listen. I play the chord for you.",
                "Copy it. Press the keys highlighted on the keyboard picture, all together. "
                "Green means right, red means not in the chord.",
                "Let go, then play it once more with the picture hidden. Any order or octave is fine.",
            ])
        return ("Chords from memory",
                "Finding chords without looking them up is what lets you follow a singer or a song you half-know.", [
            "A chord name appears in big letters (sometimes as a number in a key, like vi in C).",
            "Play it. Any inversion or octave counts.",
            "If you miss it twice, I show it to you again. H shows it any time.",
        ])

    # ---- view -----------------------------------------------------------------------------
    def view(self, now) -> View:
        new = self.mode == "new"
        title = {"guided": "Copy the shape", "recall": "From memory"}[self.phase]
        if new:
            title = f"New chord · {title.lower()}"
        if self.roman and self.prompt_key and self.phase != "guided":
            big = self.roman
            caption = f"in {self.prompt_key.name}"
        else:
            big = self.chord.symbol
            caption = self.chord.name
        lesson = ""
        if self.phase == "guided" or (new and self.phase == "recall"):
            lesson = chord_lesson(self.chord)
        if self.phase == "guided":
            piano = PianoView(held=frozenset(self.ctx.held), target=self.target, good_pcs=self.chord.pcs,
                              roots=frozenset(n for n in self.target if n % 12 == self.chord.root.pc))
        else:
            piano = PianoView(held=frozenset(self.ctx.held))
        if self.blocked:
            feedback, tone = "Release all keys to begin.", "info"
        else:
            feedback, tone = self.feedback, self.tone
        return View(block=self.block, title=title, big=big, caption=caption, lesson=lesson,
                    key=f"Key: {self.prompt_key.name}" if self.prompt_key else "",
                    piano=piano, feedback=feedback, tone=tone,
                    big_tone="good" if self.accepted else "accent",
                    listening=bool(self.ctx.demo_handle and self.ctx.demo_handle.state == "playing"))
