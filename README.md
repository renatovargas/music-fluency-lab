# Musical Fluency Lab 0.4.0

An offline, MIDI-driven piano coach for learning to recall and play chords. Launch `mfl` with a keyboard connected. Listen to the opening voicing, then play it back.

## Practice

- The seven-chord session introduces C major, A minor, F major and G major, then revisits C, Am and G from memory.
- Each new guided chord plays a short example through the default audio output. Your own notes sound as you play, with volume responding to how hard you press. Playing interrupts the example so you can start immediately.
- The piano shows the voicing and the notes you hold. Play the displayed shape with all three notes held together. You can move the entire shape to another octave. The first matching note places the guide in that octave.
- Recall hides the piano and starts without an example. Press **H** to bring back the guide and replay the example.
- Two guided successes unlock recall. Release all keys between attempts. Recall accepts any inversion or octave of the three-note chord. After two missed recall attempts, the guide returns and leads back to recall.
- Press **S** to skip, **R** to restart or **Q** to quit. The session ends with an invitation to play a favorite song. The controller keeps sounding while MFL is open.

This version tracks guided attempts, unassisted recall and skips separately in the existing SQLite history. Movement in `mfl history` is the total semitone change between voicings. The database lives at `$XDG_DATA_HOME/mfl/progress.sqlite3` or defaults to `~/.local/share/mfl/progress.sqlite3`.

The app starts the same session each time. It uses simultaneous three-note chords and has no sustain-pedal processing or interrupted-session resume. The built-in sound is synthesized locally and needs no soundfont download. If the audio device is unavailable, visual practice remains playable.

## Install and run

From the repository directory, with Python 3.11 or later and `uv` available:

```sh
uv tool install --force .
mfl
```

On Fedora 44, MIDI installation was tested with `uv tool install --force --python /usr/bin/python3 .`. A source build of `python-rtmidi` on that machine required ALSA and Python development headers. On Linux, software audio uses the system PortAudio library (`portaudio` on Arch and Fedora). On Omarchy, MFL opened the Launchkey Mini MK3 and rendered a demonstration to the default audio output. Apple Silicon still needs live verification.

- `mfl devices` lists available MIDI input ports.
- `mfl --device Launchkey` selects a matching input if the automatic choice is wrong.
- `mfl --silent` turns off software audio if your keyboard has its own sound.
- `mfl history` shows recent attempts and completed sessions.

Run the automated tests with `uv run --with pytest pytest -q`.

License is MIT. See [LICENSE](LICENSE).
