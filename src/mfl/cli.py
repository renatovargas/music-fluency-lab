"""Command line entry points."""
import typer

app = typer.Typer(help="Open your piano coach. No exercise selection required.", no_args_is_help=False)

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, device: str = typer.Option(None, "--device", help="Optional MIDI device name substring")):
    if ctx.invoked_subcommand is None:
        from mfl.tui import MFLApp
        MFLApp(preferred=device).run()

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
    for chord, success, seconds, distance in db.last_attempts():
        typer.echo(f"{chord:4} {'OK' if success else 'SKIP':4} {seconds:>5}s  movement={distance if distance is not None else '-'}")
    db.close()

if __name__ == "__main__":
    app()
