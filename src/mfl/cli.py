"""Command line entry points."""
import typer

app = typer.Typer(help="Open your piano coach. No exercise selection required.", no_args_is_help=False)

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    device: str = typer.Option(None, "--device", help="Optional MIDI device name substring"),
    silent: bool = typer.Option(False, "--silent", help="Practice without software audio"),
):
    if ctx.invoked_subcommand is None:
        from mfl.tui import MFLApp
        MFLApp(preferred=device, sound=not silent).run()

@app.command()
def devices():
    """List available MIDI input ports."""
    import rtmidi
    ports = rtmidi.MidiIn().get_ports()
    for i, name in enumerate(ports):
        typer.echo(f"{i}: {name}")
    if not ports:
        typer.echo("No MIDI ports found.")

@app.command()
def history():
    """Show recent chord attempts."""
    from mfl.storage import Progress
    db = Progress()
    typer.echo(f"Completed sessions: {db.completed_sessions()}")
    modes = {"chord": "legacy", "chord_guided": "guided", "chord_recall": "recall", "chord_skip": "skip"}
    for chord, success, seconds, distance, exercise in db.last_attempts(include_exercise=True):
        outcome = "OK" if success else "SKIP" if exercise in {"chord", "chord_skip"} else "MISS"
        movement = distance if distance is not None else "-"
        typer.echo(f"{chord:4} {outcome:4} {modes[exercise]:6} {seconds:>5}s  movement={movement}")
    db.close()

if __name__ == "__main__":
    app()
