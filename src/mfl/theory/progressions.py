"""Common-practice and popular progressions, written as Roman numerals.

Chord progressions are shared musical vocabulary, not compositions. The
descriptions name the idiom, never a specific song.
Bars are separated by ``|``. Chords inside a bar share its beats equally.
"""

from __future__ import annotations

from dataclasses import dataclass

from mfl.theory.chords import Chord
from mfl.theory.keys import Key


@dataclass(frozen=True)
class Progression:
    id: str
    name: str
    mode: str  # "major" or "minor"
    bars_text: str
    about: str
    styles: tuple[str, ...] = ()

    @property
    def bars(self) -> list[list[str]]:
        return [bar.split() for bar in self.bars_text.split("|")]

    @property
    def romans(self) -> list[str]:
        return [roman for bar in self.bars for roman in bar]

    def timeline(self, key: Key, beats_per_bar: int = 4) -> list[tuple[float, float, str, Chord]]:
        """(start beat, length, roman, chord) for each chord in one pass."""
        events = []
        for index, bar in enumerate(self.bars):
            length = beats_per_bar / len(bar)
            for position, roman in enumerate(bar):
                events.append((index * beats_per_bar + position * length, length, roman, key.chord(roman)))
        return events

    def chords(self, key: Key) -> list[Chord]:
        return [key.chord(r) for r in self.romans]

    def symbols(self, key: Key) -> list[str]:
        return [c.symbol for c in self.chords(key)]


PROGRESSIONS: dict[str, Progression] = {p.id: p for p in (
    Progression("axis", "Four-chord pop loop", "major", "I | V | vi | IV",
                "The most common loop in pop and rock ballads. V creates tension, vi turns it bittersweet.",
                ("pop", "rock", "latin pop")),
    Progression("minor-loop", "Minor-first pop loop", "major", "vi | IV | I | V",
                "The same four chords as the pop loop, starting on vi for a more melancholy feel.",
                ("pop", "ballad")),
    Progression("doowop", "Fifties progression", "major", "I | vi | IV | V",
                "Doo-wop and countless ballads. V at the end turns back to I.",
                ("ballad", "bolero", "pop")),
    Progression("three-chord", "Three-chord song", "major", "I | IV | V | I",
                "The backbone of folk, rock and ranchera. Tonic, subdominant, dominant, home.",
                ("rock", "folk", "ranchera")),
    Progression("mixolydian", "Rock ♭VII", "major", "I | ♭VII | IV | I",
                "Borrowed ♭VII avoids V's pull for an open, anthemic rock sound.",
                ("rock",)),
    Progression("circle", "Circle of fifths", "major", "vi | ii | V | I",
                "Each root falls a fifth. The engine of standards and many Latin ballads.",
                ("ballad", "jazz", "bolero")),
    Progression("ii-V-I", "ii–V–I with sevenths", "major", "ii7 | V7 | Imaj7 | Imaj7",
                "The essential jazz cadence. Notice how each chord keeps two notes of the last.",
                ("jazz", "ballad")),
    Progression("turnaround", "I–vi–ii–V turnaround", "major", "I vi | ii V | I vi | ii V",
                "Two chords per bar. A classic way to keep a song moving at the end of a section.",
                ("jazz", "pop", "bolero")),
    Progression("andalusian", "Andalusian cadence", "minor", "i | ♭VII | ♭VI | V",
                "A descending bass from flamenco to Latin pop. The major V is the dramatic turn.",
                ("latin", "flamenco", "ballad")),
    Progression("minor-plagal", "Minor plagal sway", "minor", "i | iv | i | V",
                "i and iv sway, then V returns home. A staple of minor-key boleros and rancheras.",
                ("bolero", "ranchera", "latin")),
    Progression("bolero-minor", "Minor cadence with dominant seventh", "minor", "i | iv | V7 | i",
                "The dominant seventh adds a stronger resolution, typical of romantic Latin ballads.",
                ("bolero", "latin")),
    Progression("borrowed-iv", "Ballad with borrowed iv", "major", "I | iii | IV | iv",
                "Major IV turning minor is the bittersweet sound of the power ballad.",
                ("ballad", "pop")),
    Progression("latin-ballad", "Ballad with a secondary dominant", "major", "I | V7/vi | vi | IV | ii | V7 | I | I",
                "V7/vi (E7 in C) borrows the leading tone of vi. It is a signature of Latin romantic ballads.",
                ("bolero", "latin pop", "ballad")),
    Progression("descending-bass", "Descending-bass ballad", "major", "I | V/7 | vi | I/5 | IV | I/3 | ii | V",
                "The bass walks down the scale under slash chords, a piano-ballad hallmark.",
                ("ballad", "piano pop")),
    Progression("canon", "Canon sequence", "major", "I | V | vi | iii | IV | I | IV | V",
                "A Baroque ground-bass pattern (public domain) behind many pop songs.",
                ("pop", "classical")),
    Progression("sus-release", "Suspension and release", "major", "Isus4 | I | IVsus2 | IV",
                "Suspended chords delay the third, then resolve it. This adds motion inside one harmony.",
                ("pop", "worship", "rock")),
    Progression("blues", "Twelve-bar blues", "major", "I7 | I7 | I7 | I7 | IV7 | IV7 | I7 | I7 | V7 | IV7 | I7 | V7",
                "The 12-bar form from blues, rock and roll and boogie piano.",
                ("blues", "rock")),
    Progression("epic", "Cinematic ♭VI–♭VII–I", "major", "I | ♭VI | ♭VII | I",
                "Borrowed ♭VI and ♭VII climb to the tonic with a heroic, stadium sound.",
                ("rock", "film")),
)}
