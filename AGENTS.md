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
- Tested machine: Fedora 44, Intel/x86-64. Other Fedora 44 machines, Apple Silicon Mac Mini M5, and now an Omarchy machine running Codex. Omarchy and macOS have not yet been tested with MFL.
- Prefer Python, `uv`, lightweight dependencies, Typer CLI and Textual TUI. Keep deployment simple. Reference packaging workflow: https://renatovargas.github.io/esa-toolbox/ . Eventually publish versioned GitHub releases and installable wheels; no repository URL for MFL was established in the chat.

## Handover and current implementation

This handover was prepared 2026-11-24 (Guatemala time) from the project conversation and inspection of the actual v0.2.0 ZIP. The working tree may have changed since then: inspect it, `git status`, and tests before editing. Treat current source as authoritative for implementation, this file as product direction. Preserve unrelated owner changes.

The owner successfully ran v0.1.0 and v0.2.0 on Fedora with real MIDI. v0.1 captured chords but felt like an examiner rather than a teacher. v0.2 added explanations and live target/held-note markers. Latest feedback: “It is getting there. The extra step between showing and trying where it asks you to try it yourself, but it is actually just showing it, is a bit confusing.” The next iteration was discussed but not implemented in the browser conversation.

### Repository layout (v0.2.0)

- `pyproject.toml`: Hatchling, Python >=3.11, dependencies `textual>=0.80`, `typer>=0.12`, `python-rtmidi>=1.5`; console script `mfl = mfl.cli:app`.
- `src/mfl/cli.py`: launch by default, optional `--device` substring, `devices` and `history` commands.
- `src/mfl/midi.py`: RtMidi input, filters DAW and MIDI Through ports, prefers Launchkey/Roland, polls note-on/off (including zero-velocity note-on). No fixed ALSA IDs.
- `src/mfl/theory.py`: chord pitch classes, note names, exact three-note triad matching (any inversion/octave), minimum total semitone voicing distance. MIDI cannot reveal actual fingering; call this a voicing-distance proxy.
- `src/mfl/coach.py`: `Step` and fixed `SESSION` of C, Am, F, G, C, Am, G. Not yet an adaptive coach.
- `src/mfl/tui.py`: Textual `MFLApp`, 20 ms MIDI polling, held-note state, show/guided/recall phases, target voicings and explanations, release-to-advance, hint/skip/restart controls.
- `src/mfl/storage.py`: SQLite `Progress`, attempts table (timestamp, exercise, chord, success, seconds, voicing, distance), session-complete marker. Database: `$XDG_DATA_HOME/mfl/progress.sqlite3` or `~/.local/share/mfl/progress.sqlite3` (same fallback on macOS).
- `tests/test_theory.py`: initial theory tests. Expand coverage; do not mistake these for end-to-end MIDI tests.
- `README.md`, `LICENSE` (MIT). README still begins with v0.1 heading and appends v0.2 notes; update alongside changes.

Current example voicings: C = 60,64,67 (C4 E4 G4); Am = 60,64,69 (C4 E4 A4, first inversion); F = 60,65,69 (C4 F4 A4, second inversion); G = 59,62,67 (B3 D4 G4, first inversion). C to Am changes only G to A; Am to F changes only E to F. Guided mode requires exact MIDI pitches; recall accepts any inversion/octave. Current implementation recognizes exactly three held notes, not doubled notes or arpeggios; no pedal processing, audio synthesis, adaptive scheduling, or interrupted-session resume. Each launch starts the same fixed session; history persists. Skips record unsuccessful attempts; session completion is not proof of mastery.

## Immediate next task: v0.3 — remove friction and improve visual teaching

Implement the following before broad feature expansion. These are the agreed direction plus concrete engineering recommendations for Codex to validate against the working tree.

1. Merge SHOW and guided PLAY into one interactive stage. Show the target and concise explanation, immediately accept MIDI input, and give live feedback. Remove the mandatory “I've looked — let me try” button and the manual “Hide hints — test recall” progression. Hint should restore playable guidance, never a dead-end show-only state.
2. Make the coach automatically transition from guided practice to recall after a suitable number of successful attempts. Start with a small configurable policy (e.g. two guided successes, then recall); this count is a proposed default, not a user-approved fixed rule. Require release or an appropriate new attempt boundary to prevent held notes from satisfying successive tasks. If recall fails repeatedly, restore guidance and schedule another recall later. Keep skip/quit available. Distinguish assisted and unassisted successes in data if possible without breaking existing history.
3. Replace the chromatic text grid with a recognizable piano layout: white keys with black keys in groups of two and three, correctly aligned, octave-aware, readable in a terminal. Use Textual/Rich or a custom widget rather than introduce a web stack just for this. Show target, held-correct and held-other states with distinct markers as well as color; hide targets in recall. Display actual played notes, including notes outside the target register. The v0.2 grid starts at C4, so its G voicing's B3 is invisible; its variable-width header also misaligns with the markers. Fix both. Keep layout responsive to terminal size.
4. Make instruction and acceptance rules consistent: v0.2 says “Any inversion is fine” even when exact pitches are required. In guided mode name the specific voicing and show the register; in recall explicitly say whether any inversion or the demonstrated one is accepted. Avoid telling the learner to listen to a software-generated sound until audio exists. Allow octave-equivalent guided shapes if deliberately supported and tested; otherwise make octave-shift instructions clear.
5. Preserve feedback long enough to be useful; v0.2 can overwrite wrong-chord feedback in the same poll cycle. Ensure a correct chord is recorded once, release advances correctly, hints/skips cannot double-count or accidentally carry held notes into a new task, and completion is unambiguous. Avoid arbitrary time pressure. Test with simulated MIDI events.

Acceptance: launch with a connected Mini, see a familiar keyboard and C major guidance, play immediately without clicking, receive accurate feedback, progress automatically to recall and subsequent chords, request help without blocking input, see B3 correctly, and retain existing history. No exercise menu. Owner should be able to test on hardware; do not claim live validation without it.

## Subsequent roadmap (prioritize after v0.3)

1. **Persistent coach and resume.** Separate lesson policy/state from UI and MIDI. Persist session/step/phase, skill state and attempts with backward-compatible migrations. Resume automatically after interruption, choose the next daily lesson based on actual performance, and avoid endless repetition of the same seven chords. Use stable exercise IDs and distinguish skips, guided attempts, recall and assessment. Keep data local; no account or network requirement.
2. **Audio and ear–hand training.** Add a portable, low-latency audio backend (FluidSynth was proposed, not selected or implemented). The Mini is a controller, not a piano sound source. Teach with original phrases: listen → imagine/sing → play; progressively remove visual cues. Add screen-off or auditory-only tests. Singing cannot be verified from MIDI alone; microphone analysis would be a separate optional capability.
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

Install/update locally: `uv tool install --force .` then `mfl`. On Fedora the working installation explicitly used `--python /usr/bin/python3`. On Fedora 44, `python-rtmidi==1.5.8` attempted a source build and failed first for missing ALSA headers, then Python development headers. Installing `alsa-lib-devel` and `python3-devel` and using the matching system interpreter resolved the test. JACK absence was only a warning. Other build tools were already available. For Omarchy (Arch-based), inspect the environment and wheel availability first; if compiling, ALSA development files normally come with `alsa-lib`, and compiler/build tools with `base-devel`. Do not blindly run privileged installation commands. On macOS, verify CoreMIDI and Apple Silicon wheel availability; source builds may need Xcode command line tools. No macOS/Omarchy hardware success has been established.

The tested Fedora device appeared as ALSA client 20, port 0 (`Launchkey Mini MK3 MIDI Port`); port 1 is DAW control. IDs can change. `aconnect -l` and `mfl devices` are useful diagnostics. Real note-on/off and velocity events were observed. Auto-detect by suitable port names, not fixed IDs; retain manual override for exceptional cases.

## Working agreement with the owner

The owner wants to spend time playing, not managing lessons or copying code from chat. Act as a collaborative developer: inspect the repository, implement the next coherent increment, run available tests, explain concise installation/testing steps, and ask only for decisions that materially affect the project. Preserve the owner's ability to verify the work. The software is the teacher, not merely a MIDI examiner. When uncertain about a design choice, favor the simplest path that makes the learner more independent of the software over time.
