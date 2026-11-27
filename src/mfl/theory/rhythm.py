"""Accompaniment rhythms and backing grooves, expressed in beats.

Positions are beats from the start of the bar (0 = beat 1, 1.5 = the
"and" of beat 2). Comping patterns are what the learner plays. Grooves are
what the virtual band plays: General MIDI drum numbers, plus bass hits.
"""

from __future__ import annotations

from dataclasses import dataclass

# General MIDI percussion numbers used by the built-in drum kit.
KICK, RIM, SNARE, CLAP, HAT, HAT_OPEN, SHAKER = 36, 37, 38, 39, 42, 46, 70
BONGO_HI, BONGO_LO, CONGA_HI, CONGA_LO, CONGA_OPEN = 60, 61, 62, 63, 64
CLAVES, CLICK_HI, CLICK_LO, COWBELL = 75, 76, 77, 56


@dataclass(frozen=True)
class CompPattern:
    id: str
    name: str
    onsets: tuple[float, ...]
    about: str
    groove: str = "ballad"
    beats_per_bar: int = 4
    single_tones: bool = False  # True: each hit is one chord tone (broken chord)

    def bar_onsets(self, bar_start: float) -> list[float]:
        return [bar_start + o for o in self.onsets]

    @property
    def counting(self) -> str:
        """A count line such as ``1 . 2 & 3 . 4 .`` with hits marked."""
        cells = []
        for eighth in range(self.beats_per_bar * 2):
            beat = eighth / 2
            label = str(eighth // 2 + 1) if eighth % 2 == 0 else "&"
            cells.append(label if beat in self.onsets else "·")
        return " ".join(cells)


COMP_PATTERNS: dict[str, CompPattern] = {p.id: p for p in (
    CompPattern("whole", "Change on beat 1", (0,),
                "One chord at the start of each bar. Listen to the band and land on time.", "ballad"),
    CompPattern("halves", "Ballad half notes", (0, 2),
                "Beats 1 and 3. The calm pulse of a slow ballad.", "ballad"),
    CompPattern("quarters", "Steady quarters", (0, 1, 2, 3),
                "Four even chords per bar. Keep them even and relaxed.", "pop"),
    CompPattern("pop8", "Pop eighths", (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5),
                "Driving eighth notes, piano-rock style. Lean into beats 1 and 3.", "rock"),
    CompPattern("charleston", "Charleston", (0, 1.5),
                "Beat 1 and the 'and' of 2. A light, syncopated push.", "pop"),
    CompPattern("tresillo", "Tresillo 3+3+2", (0, 1.5, 3),
                "The 3+3+2 cell at the root of Latin, reggaetón and pop syncopation.", "latin"),
    CompPattern("habanera", "Habanera", (0, 1.5, 2, 3),
                "Tresillo with beat 3 filled in. The Cuban habanera and tango pulse.", "latin"),
    CompPattern("cinquillo", "Cinquillo", (0, 1, 1.5, 2.5, 3),
                "A five-stroke Cuban cell heard in danzón and bolero accompaniment.", "bolero"),
    CompPattern("arpeggio", "Broken chord eighths", (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5),
                "Play one chord tone per eighth note: low, middle, high, middle… The ballad flow.",
                "ballad", single_tones=True),
    CompPattern("waltz", "Waltz (3/4)", (0, 1, 2),
                "Three beats per bar. Lean on beat 1. Valses and slow 3/4 ballads.", "waltz", 3),
)}

# Groove: list of (beat, drum, velocity). Bass plays roots on the listed beats.
GROOVES: dict[str, dict] = {
    "ballad": {
        "drums": [(0, KICK, 80), (1, RIM, 60), (2, KICK, 64), (3, RIM, 64),
                  *[(b / 2, SHAKER, 38 if b % 2 else 48) for b in range(8)]],
        "bass": (0, 2),
    },
    "pop": {
        "drums": [(0, KICK, 96), (1, SNARE, 80), (2, KICK, 88), (2.5, KICK, 60), (3, SNARE, 84),
                  *[(b / 2, HAT, 52 if b % 2 else 66) for b in range(8)]],
        "bass": (0, 2, 2.5),
    },
    "rock": {
        "drums": [(0, KICK, 104), (1, SNARE, 96), (2, KICK, 96), (2.5, KICK, 76), (3, SNARE, 100),
                  *[(b / 2, HAT, 60 if b % 2 else 78) for b in range(8)]],
        "bass": (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5),
    },
    "latin": {
        "drums": [(0, KICK, 80), (1.5, KICK, 60), (2, KICK, 76), (3.5, KICK, 60),
                  (1, CLAVES, 64), (2, CLAVES, 64), (3.5, CONGA_HI, 60), (3, CONGA_OPEN, 70),
                  *[(b / 2, SHAKER, 40 if b % 2 else 52) for b in range(8)]],
        "bass": (0, 1.5, 3),
    },
    "bolero": {
        "drums": [(0, KICK, 66), (2, KICK, 58), (0, BONGO_LO, 52), (0.5, BONGO_HI, 38),
                  (1, BONGO_HI, 56), (1.5, BONGO_HI, 40), (2, BONGO_LO, 50), (2.5, BONGO_HI, 40),
                  (3, BONGO_HI, 60), (3.5, BONGO_LO, 46), (1, CLAVES, 52), (2.5, CLAVES, 48),
                  *[(b / 2, SHAKER, 34 if b % 2 else 44) for b in range(8)]],
        "bass": (0, 2),
    },
    "waltz": {
        "drums": [(0, KICK, 76), (1, RIM, 50), (2, RIM, 50), *[(b / 2, SHAKER, 36) for b in range(6)]],
        "bass": (0,),
        "beats": 3,
    },
}


def metronome(beats_per_bar: int = 4) -> list[tuple[float, int, int]]:
    return [(0, CLICK_HI, 110)] + [(b, CLICK_LO, 80) for b in range(1, beats_per_bar)]


def bpm_seconds(bpm: float) -> float:
    return 60.0 / bpm
