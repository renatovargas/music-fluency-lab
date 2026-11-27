"""Terminal renderers: big chord symbols, a colour piano, a rhythm lane,
a chord chart and chips. Each returns a ``rich.text.Text``."""

from __future__ import annotations

from rich.text import Text

from mfl.exercises.base import ChartView, LaneView, PianoView
from mfl.theory.pitch import LETTERS, is_black

# ---------------------------------------------------------------------------
# Big text: a 5-pixel-high font drawn with half blocks (3 terminal rows).
# ---------------------------------------------------------------------------

_GLYPHS = {
    "A": ".##.|#..#|####|#..#|#..#", "B": "###.|#..#|###.|#..#|###.", "C": ".###|#...|#...|#...|.###",
    "D": "###.|#..#|#..#|#..#|###.", "E": "####|#...|###.|#...|####", "F": "####|#...|###.|#...|#...",
    "G": ".###|#...|#.##|#..#|.###", "I": "###|.#.|.#.|.#.|###", "V": "#...#|#...#|#...#|.#.#.|..#..",
    "M": "#...#|##.##|#.#.#|#...#|#...#", "L": "#...|#...|#...|#...|####",
    "0": "###|#.#|#.#|#.#|###", "1": ".#.|##.|.#.|.#.|###", "2": "###|..#|###|#..|###",
    "3": "###|..#|.##|..#|###", "4": "#.#|#.#|###|..#|..#", "5": "###|#..|###|..#|###",
    "6": "###|#..|###|#.#|###", "7": "###|..#|.#.|.#.|.#.", "8": "###|#.#|###|#.#|###",
    "9": "###|#.#|###|..#|###",
    "a": "...|...|.##|#.#|.##", "d": "..#|..#|.##|#.#|.##", "i": "#|.|#|#|#", "j": "..#|...|..#|..#|##.",
    "m": ".....|.....|####.|#.#.#|#.#.#", "s": "...|...|.##|.#.|##.", "u": "...|...|#.#|#.#|.##",
    "v": "...|...|#.#|#.#|.#.", "o": "...|...|.#.|#.#|.#.", "b": "#..|#..|###|#.#|##.",
    "♭": "#..|#..|###|#.#|##.", "♯": ".#.#.|#####|.#.#.|#####|.#.#.", "#": ".#.#.|#####|.#.#.|#####|.#.#.",
    "/": "..#|..#|.#.|#..|#..", "+": "...|.#.|###|.#.|...", "°": ".#.|#.#|.#.|...|...",
    "ø": ".##.|#.##|##.#|.##.|....", "?": ".##.|#..#|..#.|....|..#.", "·": ".|.|#|.|.", "(": ".#|#.|#.|#.|.#",
    ")": "#.|.#|.#|.#|#.", "♪": ".##.|.#.#|.#..|##..|##..", "●": "...|###|###|###|...",
    "○": "...|###|#.#|###|...", "★": "..#..|#####|.###.|.#.#.|#...#", " ": "..|..|..|..|..", "-": "...|...|###|...|...",
}


def big_text(text: str, style: str = "bold") -> Text | None:
    """Render ``text`` in the block font, or None if a character is missing."""
    if not text or any(ch not in _GLYPHS for ch in text):
        return None
    glyphs = [_GLYPHS[ch].split("|") for ch in text]
    rows = ["".join(g[r] + "." for g in glyphs) for r in range(5)] + ["." * sum(len(g[0]) + 1 for g in glyphs)]
    result = Text(no_wrap=True)
    for top, bottom in ((0, 1), (2, 3), (4, 5)):
        for a, b in zip(rows[top], rows[bottom]):
            result.append({("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄"}.get((a, b), " "), style)
        if top < 4:
            result.append("\n")
    return result


# ---------------------------------------------------------------------------
# Piano.
# ---------------------------------------------------------------------------

WHITE_BG, BLACK_BG, EDGE = "#ece8df", "#1c1c22", "#8a8578"
HELD, GOOD, BAD, TARGET, ROOT = "#5b8def", "#3fbf6a", "#e5534b", "#2bb3c0", "#1d8a96"
TONIC = "#c9a227"
WHITE_PCS = (0, 2, 4, 5, 7, 9, 11)
HAS_BLACK_AFTER = {0, 2, 5, 7, 9}  # C, D, F, G, A have a black key to their right


def _key_color(note: int, view: PianoView) -> str | None:
    if note in view.held:
        if view.good_pcs is None:
            return HELD
        return GOOD if note % 12 in view.good_pcs else BAD
    if note in view.target:
        return ROOT if note in view.roots else TARGET
    return None


def piano_range(view: PianoView, width: int) -> tuple[int, int, int]:
    """Choose (low, high, key width) covering every note of interest."""
    interest = set(view.held) | set(view.target) | set(view.marks)
    low = view.low if view.low is not None else min(interest | {53})
    high = view.high if view.high is not None else max(interest | {77})
    low -= low % 12  # start on C
    high += 11 - high % 12  # end on B
    whites = sum(1 for n in range(low, high + 1) if not is_black(n))
    for key_width in (4, 3, 2):
        if whites * key_width + 1 <= width:
            return low, high, key_width
    # Too wide: crop to two octaves around the notes of interest.
    centre = (min(interest) + max(interest)) // 2 if interest else 64
    low = max(0, centre - 12 - (centre - 12) % 12)
    return low, low + 35, 2


def piano(view: PianoView, width: int = 80) -> Text:
    """Draw the keyboard: held keys green (right) or red (wrong), or blue when
    no judgement applies. Target keys are teal, and tonic keys carry a small ▪."""
    low, high, w = piano_range(view, width)
    whites = [n for n in range(low, high + 1) if not is_black(n)]
    columns = len(whites) * w
    black_at: dict[int, int] = {}
    first_col: dict[int, int] = {}
    for i, n in enumerate(whites):
        if n % 12 in HAS_BLACK_AFTER and n + 1 <= high and i + 1 < len(whites):
            boundary = (i + 1) * w
            cols = [boundary - 1, boundary] if w >= 3 else [boundary]
            first_col[n + 1] = cols[0]
            for col in cols:
                black_at[col] = n + 1
    result = Text(no_wrap=True)
    for row in range(5):
        for col in range(columns):
            white = whites[col // w]
            white_color = _key_color(white, view)
            white_bg = white_color or WHITE_BG
            if row < 3 and col in black_at:
                note = black_at[col]
                color = _key_color(note, view)
                fill = color or BLACK_BG
                if row == 2:
                    result.append("▀", f"{fill} on {white_bg}")
                    continue
                ch, fg = " ", "#ffffff"
                if row == 1 and col == first_col[note]:
                    if note in view.marks:
                        ch = view.marks[note][0]
                    elif note % 12 in view.tonic_pcs and not color:
                        ch, fg = "▪", TONIC
                result.append(ch, f"bold {fg} on {fill}")
                continue
            if col % w == 0:
                result.append("▏", f"{EDGE} on {white_bg}")
                continue
            ch, fg = " ", "#ffffff" if white_color else "#555049"
            if row == 4 and col % w == 1:
                if white in view.marks:
                    ch = view.marks[white][0]
                elif white_color:
                    ch = LETTERS[WHITE_PCS.index(white % 12)]
                elif white % 12 in view.tonic_pcs:
                    ch, fg = "▪", TONIC
            result.append(ch, f"bold {fg} on {white_bg}")
        result.append("▕\n", EDGE)
    labels = [" "] * columns
    for i, n in enumerate(whites):
        if n % 12 == 0:
            for k, ch in enumerate(f"C{n // 12 - 1}"):
                if i * w + k < columns:
                    labels[i * w + k] = ch
    result.append("".join(labels), "dim")
    return result


# ---------------------------------------------------------------------------
# Rhythm lane.
# ---------------------------------------------------------------------------

STATUS_STYLE = {
    "upcoming": ("◆", "bold #c8c8c8"), "good": ("●", "bold #3fbf6a"), "ok": ("●", "bold #9acd32"),
    "early": ("◀", "bold #e0b400"), "late": ("▶", "bold #e0b400"), "wrong": ("✕", "bold #e5534b"),
    "missed": ("○", "#e5534b"), "example": ("♪", "bold #5b8def"),
}


def lane(view: LaneView, width: int = 72) -> Text:
    usable = max(16, width - 2)
    per_beat = usable / view.window_beats

    def column(beat: float) -> int:
        return int(round((beat - view.window_start) * per_beat))

    cursor = column(view.now) if view.window_start <= view.now < view.window_start + view.window_beats else None
    label_row = [" "] * usable
    for beat, text in view.labels:
        c = column(beat)
        for k, ch in enumerate(text[: max(1, int(per_beat * view.beats_per_bar) - 1)]):
            if 0 <= c + k < usable:
                label_row[c + k] = ch
    ruler, count = ["─"] * usable, [" "] * usable
    for eighth in range(int(view.window_beats * 2)):
        beat = view.window_start + eighth / 2
        c = column(beat)
        if not 0 <= c < usable:
            continue
        local = eighth / 2 % view.beats_per_bar
        if eighth % 2:
            count[c] = "&"
        else:
            ruler[c] = "┃" if local == 0 else "┊"
            count[c] = str(int(local) + 1)
    hits: list[tuple[str, str]] = [(" ", "")] * usable
    for beat, status in view.expected:
        c = column(beat)
        if 0 <= c < usable:
            hits[c] = STATUS_STYLE.get(status, ("◆", ""))
    for beat in view.strays:
        c = column(beat)
        if 0 <= c < usable and hits[c][0] == " ":
            hits[c] = ("×", "bold #d070d0")
    result = Text(no_wrap=True)
    if view.banner:
        result.append(view.banner + "\n", "bold")
    rows = [
        [(ch, "bold cyan") for ch in label_row],
        [(ch, "#6c6c7a") for ch in ruler],
        hits,
        [(ch, "dim") for ch in count],
    ]
    for r, row in enumerate(rows):
        result.append(" ")
        for c, (ch, style) in enumerate(row):
            if c == cursor:
                result.append(ch if ch != " " else ("▼" if r == 0 else "│"), (style or "") + " on #3a3a55")
            else:
                result.append(ch, style)
        if r < len(rows) - 1:
            result.append("\n")
    return result


# ---------------------------------------------------------------------------
# Chord chart and chips.
# ---------------------------------------------------------------------------

def chart(view: ChartView, width: int = 72) -> Text:
    cell = max(7, max((len(c) for c in view.cells), default=1) + 3)
    per_row = max(1, min(view.per_row, (width - 1) // (cell + 1)))
    result = Text(no_wrap=True)
    if view.caption:
        result.append(view.caption + "\n", "dim")
    for start in range(0, len(view.cells), per_row):
        if start:
            result.append("\n")
        result.append("│", "#6c6c7a")
        for i in range(start, min(start + per_row, len(view.cells))):
            text = f" {view.cells[i]}".ljust(cell)
            status = view.statuses.get(i)
            if i == view.current:
                style = "bold #10101a on #e0b84a"
            elif status == "good":
                style = "#3fbf6a"
            elif status == "miss":
                style = "#e5534b"
            elif status == "hint":
                style = "#e0b400"
            else:
                style = "bold"
            result.append(text, style)
            result.append("│", "#6c6c7a")
    return result


def chips(labels: list[str], highlight: int | None = None, wrong: int | None = None) -> Text:
    result = Text(no_wrap=False)
    for i, label in enumerate(labels):
        if i == highlight:
            style = "bold #10101a on #3fbf6a"
        elif i == wrong:
            style = "bold #ffffff on #e5534b"
        else:
            style = "#d0d0dc on #2c2c3a"
        result.append(f" {label} ", style)
        result.append(" ")
    return result


def meter(level: float, width: int = 10) -> Text:
    filled = int(round(min(1.0, level) * width))
    color = "#3fbf6a" if level < 0.7 else "#e0b400" if level < 0.95 else "#e5534b"
    return Text("█" * filled, color) + Text("░" * (width - filled), "#44445a")
