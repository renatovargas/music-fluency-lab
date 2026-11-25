"""First guided session: no selection of keys or exercises."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Step:
    chord: str
    instruction: str

# A short assessment that revisits familiar chords and introduces a gentle challenge.
SESSION = (
    Step("C", "Play C major. Any inversion is fine."),
    Step("Am", "Now A minor. Keep the movement small."),
    Step("F", "Find F major. Take your time."),
    Step("G", "Now G major. Listen to the change."),
    Step("C", "Return to C major without looking at a chart."),
    Step("Am", "A minor again. Can you recall it faster?"),
    Step("G", "One last G major, then you're done."),
)
