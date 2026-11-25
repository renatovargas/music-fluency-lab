# AGENTS.md — Musical Fluency Lab (MFL)

## Mission and product philosophy

MFL is an offline-first, MIDI-driven personal piano coach and an experimental learning project. Its purpose is **practical musical fluency, not repertoire accumulation or theoretical knowledge alone**: hear, anticipate, recall, accompany, improvise and create music without depending on chord charts. The aspirational outcome is a living-room pianist who can accompany friends singing, transpose for a singer, recover from mistakes, and add tasteful fills. Pop/rock and Latin ballads are the primary musical laboratory; borrow jazz learning techniques and harmonic vocabulary in service of that goal, not as a prerequisite.

The owner calls the desired experience **Miyagi Sensei** (wax on, wax off). This is a non-negotiable product requirement:

- Opening `mfl` should automatically connect the keyboard, resume where the learner left off, and prescribe the next task. Never require the learner to choose a scale, key, exercise, difficulty or curriculum before practicing.
- Teach before testing. Demonstrate a movement or musical idea, let the learner imitate with feedback, then remove assistance and test recall. Reintroduce support when needed. Short explanations are welcome; long theory lectures are not.
- Minimize computer interaction: playing the MIDI keyboard should drive progress. No mandatory confirmation clicks between seeing a chord and trying it. Optional hint, skip, quit and accessibility controls are fine.
- Make every exercise musically meaningful. Preserve the pleasure of playing; finish sessions with an invitation to play a favorite song freely. Do not turn all piano time into homework or optimize solely for exercise scores.
- Prefer durable retrieval and transfer to unfamiliar music over short-term performance on repeated exercises. Speed is useful only alongside accuracy, musicality and retention. Accelerated learning is a hypothesis to test, not a validated promise.

## Learner and target environment

The owner is an experienced programmer/economist, not a beginning musician. He can sing while accompanying himself from chord charts, understands major/minor triads and some inversions, and uses economical voicings on a small Casiotone. C major/A minor and, to a lesser extent, G major/E minor are familiar. Other keys make sense during practice but do not stick. Ear-to-hand connection, harmonic prediction, spontaneous retrieval across keys, and accompaniment fluency are the principal bottlenecks. Do not assume his precise ear-training level before assessing it.

- Practice budget: 20–30 minutes/day, five days/week, including enjoyable free playing.
- Musical references: Elton John, Billy Joel, Alicia Keys (*If I Ain't Got You*), Fito Páez (*11 y 6*), Ricardo Arjona, Luis Miguel, Ana Gabriel. These are stylistic goals, not a request to embed copyrighted song transcriptions. Use original short musical examples for built-in exercises.
- Owner shared a performance of *Your Song*: https://youtu.be/q39nQeKKrFk . Previous assistant could not access the performance; do not claim it was evaluated.
- Primary portable controller: Novation Launchkey Mini MK3 (25 keys), USB. Also Launchkey 49 and Roland FP-30X (88 keys). Exercises must fit the available register or adapt intelligently. Do not require two-handed full-range playing on the Mini.
- Tested machine: Fedora 44, Intel/x86-64. Other Fedora 44 machines, Apple Silicon Mac Mini M5, and now an Omarchy machine running Codex. The owner tested v0.4 with the Launchkey Mini MK3 on Omarchy. Apple Silicon still needs live verification.
- Prefer Python, `uv`, lightweight dependencies, Typer CLI and Textual TUI. Keep deployment simple. Reference packaging workflow: https://renatovargas.github.io/esa-toolbox/ . Eventually publish versioned GitHub releases and installable wheels; no repository URL for MFL was established in the chat.

## Handover and current implementation

The original handover was prepared on 2026-11-24 from the v0.2.0 ZIP. The owner successfully ran v0.1 and v0.2 on Fedora. v0.1 felt like an examiner, and v0.2 introduced guidance but required an intermediate click that made it unclear when to play. The current checkout implements v0.3 and v0.4. Inspect the working tree and tests before editing, and preserve unrelated owner changes.

### Current implementation (v0.4.0)

- `src/mfl/cli.py` launches practice by default, supports `--device` and `--silent`, and provides `devices` and `history`. `src/mfl/midi.py` auto-selects a suitable input, prefers Launchkey/Roland, ignores DAW and MIDI Through ports, and treats zero-velocity note-on as note-off.
- `src/mfl/coach.py` runs the fixed C–Am–F–G–C–Am–G session. The first four chords open in playable guidance, and the final three open in recall. The current defaults are two guided successes before recall and two missed recalls before guidance returns. Release separates attempts. Hint restores playable guidance, and skip remains available.
- `src/mfl/tui.py` uses Textual and polls MIDI every 20 ms. `src/mfl/keyboard.py` draws octave-aware black and white keys with distinct target and held markers. The guide can move an entire voicing by octaves, displays B3, and shows notes outside the target range. Recall hides the piano diagram while keeping the held-note readout.
- `src/mfl/audio.py` uses a local NumPy synth with sounddevice/PortAudio. Each new guided chord plays a short example. The learner's MIDI notes produce velocity-sensitive sound, including in recall and after session completion while the app stays open. Playing interrupts the demonstration. H replays it in guidance or restores guidance in recall. Audio startup failure leaves visual practice available.
- `src/mfl/theory.py` handles pitch classes, note names, exact three-note triads, and the voicing-distance proxy. Guide shapes are C4–E4–G4, C4–E4–A4, C4–F4–A4 and B3–D4–G4. Guidance accepts the same shape shifted by octaves. Recall accepts any inversion or octave. Doubles, arpeggios and pedal processing are unsupported.
- `src/mfl/storage.py` keeps SQLite history at `$XDG_DATA_HOME/mfl/progress.sqlite3` or `~/.local/share/mfl/progress.sqlite3`. It preserves legacy rows and distinguishes guided practice, recall and skips. Launch still starts the fixed lesson from the beginning. Session completion is not proof of mastery.
- The 10 automated tests cover theory, coach release boundaries and recovery, register mapping, MIDI decoding, history compatibility, the headless Textual flow, and synth pitch and release. They use fake MIDI and temporary progress databases.

### Hardware feedback and next task

The owner installed v0.4 on Omarchy with `uv tool install --force --python /usr/bin/python3 .` and confirmed that the Launchkey Mini MK3 produces sound. No system package installation was needed on that machine. The sound is a little quiet. After a successful blind recall, the next guided example begins as the learner's notes are still audible, producing a double sound. The owner chose to stop for the day with both issues open.

On the next audio pass, check playback gain on hardware and leave a clear audible gap between the learner's release and the next demonstration. Keep MIDI input responsive, cancel pending examples when the learner starts playing, and verify both the automatic handoff and hint replay.

## Subsequent roadmap

1. **Persistent coach and resume.** Separate lesson policy/state from UI and MIDI. Persist session/step/phase, skill state and attempts with backward-compatible migrations. Resume automatically after interruption, choose the next daily lesson based on actual performance, and avoid endless repetition of the same seven chords. Use stable exercise IDs and distinguish skips, guided attempts, recall and assessment. Keep data local; no account or network requirement.
2. **Audio and ear–hand training.** Build on the local synth to teach with original phrases: listen → imagine/sing → play; progressively remove visual cues. Add screen-off or auditory-only tests. Singing cannot be verified from MIDI alone; microphone analysis would be a separate optional capability.
3. **Retrieval and harmonic navigation.** Spaced review across days, interleaving familiar and new keys, short targeted transition exercises, harmonic prediction and disappearing chord charts (symbols → functions → bass cues → no cues). Use functional harmony, not isolated scale drills. Test unfamiliar progressions and keys to measure transfer. Adapt challenge based on accuracy, response time and hint dependence; do not confuse quick responses with learning.
4. **Accompaniment and creativity.** Train reusable pop/rock, Latin pop, ballad and bolero-inspired patterns, economical voice leading, bass movement, rhythmic stability, dynamics, intros/fills, and transposition. Gradually introduce sevenths, ninths, secondary dominants and chromatic approaches. Add constrained improvisation, motif development and an imaginary singer (original melody with pauses and delayed entrances) to teach listening and responsive accompaniment. Keep Mini-compatible tasks and larger-keyboard tasks separate where necessary.
5. **Evaluation and distribution.** Establish baseline and periodic unassisted tests using novel material; assess melody reproduction, harmonic recognition, keyboard navigation, rhythm and creative fluency. A 14-day pilot and longer 12-week experiment were proposed, not validated. Add cross-platform CI, versioned releases, installable wheels, and a diagnostic command if useful. Avoid requiring a cloud LLM for per-note feedback; deterministic music algorithms should handle real-time evaluation. AI coaching can be optional later.

## Development and verification

Use small, testable changes. Keep theory, coach, MIDI, storage and rendering separate; avoid a large rewrite without a demonstrated need. Add tests for phase transitions, MIDI release and zero-velocity note-on, exact vs inversion matching, hint recovery, register/layout mapping, and persistence when touched. Prefer fake MIDI input and temporary SQLite databases in automated tests; never write tests into the owner's real practice database. Preserve the existing CLI and data. Update version, README, and changelog/release notes as appropriate. Report what was tested and what requires physical hardware. Do not publish or push without authorization.

Development commands (from project root):

```sh
uv sync
uv run mfl devices
uv run mfl
uv run --with pytest pytest -q
```

Install/update locally: `uv tool install --force .` then `mfl`. On Fedora the working installation explicitly used `--python /usr/bin/python3`. On Fedora 44, `python-rtmidi==1.5.8` attempted a source build and failed first for missing ALSA headers, then Python development headers. Installing `alsa-lib-devel` and `python3-devel` and using the matching system interpreter resolved the test. JACK absence was only a warning. Other build tools were already available. For Omarchy (Arch-based), inspect the environment and wheel availability first; if compiling, ALSA development files normally come with `alsa-lib`, and compiler/build tools with `base-devel`. Do not blindly run privileged installation commands. On macOS, verify CoreMIDI and Apple Silicon wheel availability; source builds may need Xcode command line tools. Omarchy live playback was confirmed in v0.4. macOS still needs hardware verification.

The tested Fedora device appeared as ALSA client 20, port 0 (`Launchkey Mini MK3 MIDI Port`); port 1 is DAW control. IDs can change. `aconnect -l` and `mfl devices` are useful diagnostics. Real note-on/off and velocity events were observed. Auto-detect by suitable port names, not fixed IDs; retain manual override for exceptional cases.

## Working agreement with the owner

The owner wants to spend time playing, not managing lessons or copying code from chat. Act as a collaborative developer: inspect the repository, implement the next coherent increment, run available tests, explain concise installation/testing steps, and ask only for decisions that materially affect the project. Preserve the owner's ability to verify the work. The software is the teacher, not merely a MIDI examiner. When uncertain about a design choice, favor the simplest path that makes the learner more independent of the software over time.
