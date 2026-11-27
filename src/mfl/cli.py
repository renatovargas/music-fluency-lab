"""Command line entry points."""

from __future__ import annotations

import typer

app = typer.Typer(help="Open your piano coach. No exercise selection required.", no_args_is_help=False,
                  add_completion=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    device: str = typer.Option(None, "--device", help="Optional MIDI device name substring"),
    silent: bool = typer.Option(False, "--silent", help="Practice without software audio"),
    minutes: float = typer.Option(None, "--minutes", help="Structured practice length (default 30)"),
):
    if ctx.invoked_subcommand is None:
        from mfl.ui.app import MFLApp

        MFLApp(preferred=device, sound=not silent, minutes=minutes).run()


@app.command()
def devices():
    """List available MIDI input ports and show which one MFL would pick."""
    from mfl.midi import choose_port, list_ports

    ports = list_ports()
    chosen = choose_port(ports)
    for i, name in enumerate(ports):
        typer.echo(f"{'→' if i == chosen else ' '} {i}: {name}")
    if not ports:
        typer.echo("No MIDI ports found.")


@app.command()
def history(limit: int = typer.Option(15, help="Rows to show")):
    """Show recent results (and legacy v0.4 chord attempts)."""
    import json

    from mfl.curriculum import SKILLS
    from mfl.srs import GRADE_WORDS
    from mfl.storage import Progress

    db = Progress()
    typer.echo(f"Completed sessions: {db.completed_sessions()}")
    for row in db.recent_results(limit):
        skill = SKILLS.get(row["skill"])
        title = skill.title if skill else row["skill"]
        word = "skip" if row["kind"].endswith("_skip") else GRADE_WORDS.get(row["grade"], "")
        summary = json.loads(row["details"] or "{}").get("summary", "")
        typer.echo(f"{row['day']}  {word:<11} {title}  {summary}")
    legacy = db.last_attempts(5, include_exercise=True)
    if legacy:
        typer.echo("\nv0.4 chord attempts:")
        modes = {"chord": "legacy", "chord_guided": "guided", "chord_recall": "recall", "chord_skip": "skip"}
        for chord, success, seconds, distance, exercise in legacy:
            outcome = "OK" if success else "SKIP" if exercise in {"chord", "chord_skip"} else "MISS"
            movement = distance if distance is not None else "-"
            typer.echo(f"{chord:4} {outcome:4} {modes[exercise]:6} {seconds:>5}s  movement={movement}")
    db.close()


@app.command()
def stats():
    """Progress overview: keys, curriculum path and recent results."""
    from rich.console import Console

    from mfl.report import report
    from mfl.storage import Progress

    db = Progress()
    Console().print(report(db))
    db.close()


@app.command()
def plan(minutes: float = typer.Option(30.0, help="Structured practice length")):
    """Show today's lesson plan without starting it."""
    from datetime import date

    from mfl.planner import describe, estimate_minutes, plan_session
    from mfl.storage import Progress

    db = Progress()
    session = db.open_session(date.today().isoformat())
    items = session["plan"][session["position"]:] if session else plan_session(db.skills(), date.today(), minutes)
    typer.echo("Resuming today's session:" if session else "Today's plan:")
    block = None
    for item in items:
        if item.get("block") != block:
            block = item.get("block")
            typer.echo(f"\n{block}")
        typer.echo(f"  · {describe(item)}")
    typer.echo(f"\n≈ {sum(estimate_minutes(i) for i in items):.0f} minutes, then free play.")
    db.close()


@app.command()
def sounds():
    """Play a short phrase on each built-in sound, then the band."""
    import time

    from mfl.audio import INSTRUMENT_NAMES, PLAYABLE, NoteEvent, open_audio
    from mfl.theory import GROOVES, Key, PROGRESSIONS, bass_note, lead_progression

    audio = open_audio()
    typer.echo(f"Output: {audio.name}. Preparing sounds…")
    audio.engine.warm_all()
    key = Key.parse("C")
    chords = PROGRESSIONS["axis"].chords(key)
    voicings = lead_progression(chords)
    try:
        for instrument in PLAYABLE:
            typer.echo(f"  {INSTRUMENT_NAMES[instrument]}")
            audio.set_instrument(instrument)
            t0 = time.perf_counter() + 0.2
            events = []
            for i, v in enumerate(voicings):
                events += [NoteEvent(t0 + i * 0.8, n, 82, 0.75) for n in v]
            audio.play(events, tag="sounds", source="backing")
            time.sleep(3.6)
        typer.echo("  The band (ballad groove with bass)")
        audio.set_instrument("piano")
        spb = 60 / 84
        t0 = time.perf_counter() + 0.2
        events = []
        for bar, (c, v) in enumerate(zip(chords, voicings)):
            base = t0 + bar * 4 * spb
            events += [NoteEvent(base + beat * spb, drum, vel, 0.1, "drums") for beat, drum, vel in GROOVES["pop"]["drums"]]
            events += [NoteEvent(base + b * spb, bass_note(c), 92, 0.9 * spb * 2, "bass") for b in (0, 2)]
            events += [NoteEvent(base + b * spb, n, 76, spb * 0.9) for b in (0, 1, 2, 3) for n in v]
        audio.play(events, tag="sounds", source="backing")
        time.sleep(16 * spb + 1.5)
    finally:
        audio.close()


@app.command()
def version():
    """Print the version."""
    from mfl import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
