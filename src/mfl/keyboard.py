"""Render MIDI pitches on a terminal piano with octave labels."""

from rich.text import Text

WHITE = (0, 2, 4, 5, 7, 9, 11)
BLACK = {3: 1, 6: 3, 12: 6, 15: 8, 18: 10}
BLACK_EDGES = {position - 1 for position in BLACK}
OCTAVE_WIDTH = 21
WHITE_STYLE = "black on white"
BLACK_STYLE = "bright_white on black"


def piano(held: set[int], target: set[int] | None, width: int) -> Text:
    octaves = sorted({4, *(note // 12 - 1 for note in held | (target or set()))})
    per_row = max(1, (width + 1) // (OCTAVE_WIDTH + 1))
    result = Text(no_wrap=True)

    def marker(note: int) -> tuple[str, str]:
        if note in held:
            return ("●", "bright_green") if target is None or note in target else ("×", "bright_yellow")
        return ("◆", "bright_cyan") if target and note in target else (" ", "")

    for start in range(0, len(octaves), per_row):
        if start:
            result.append("\n")
        group = octaves[start:start + per_row]
        for row in range(4):
            for column, octave in enumerate(group):
                if column:
                    result.append(" ")
                base = (octave + 1) * 12
                if row < 2:
                    for position in range(OCTAVE_WIDTH):
                        if position in BLACK:
                            symbol, color = marker(base + BLACK[position])
                            result.append(symbol if row else " ", f"{color} on black" if color else BLACK_STYLE)
                        elif position in BLACK_EDGES:
                            result.append(" ", BLACK_STYLE)
                        else:
                            result.append("│" if position % 3 == 2 else " ", WHITE_STYLE)
                elif row == 2:
                    for pitch in WHITE:
                        symbol, color = marker(base + pitch)
                        style = f"{color.replace('bright_', '')} on white" if color else WHITE_STYLE
                        result.append(" ", WHITE_STYLE)
                        result.append(symbol, style)
                        result.append("│", WHITE_STYLE)
                else:
                    result.append(f"C{octave}".ljust(3) + " D  E  F  G  A  B ", "dim")
            if row < 3:
                result.append("\n")
    return result
