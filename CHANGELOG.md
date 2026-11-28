# Changelog

## 0.9.1 — 2026-11-27

The end of an exercise wasn't obvious, and the next exercise's opening chords sounded like something to copy.

- **Exercise complete screen.** Finishing an exercise now shows its own screen for 3 seconds (was 1.8): "Exercise complete", a ★, your result, what comes next, and "Nothing to play right now". It used to keep the old exercise on screen, as if it were still going.
- **Key-setting chords are labelled.** The chords that open ear exercises are marked as listen-only ("These first chords only set the key. Just listen, don't play them."), in the intro cards and on screen while they play. In "Which chord?" the screen says the *last* chord is the one to find.

## 0.9.0 — 2026-11-27

The melody echo exercise was confusing: a chord progression, then some notes, and "sing it in your head". Sing what? Which key? Where do you start? Searching the keyboard for a note also entered wrong answers.

### Echo the melody (rebuilt)
- **Find your way first.** The exercise starts by playing the scale up from home ("This is the C major scale, from home (C, do)"), then you play it with the next key lit. Wrong keys here cost nothing.
- **Melody only.** No more chord cadence before each melody; the key is already in your hands and on screen.
- **Labelled keys, one octave.** The scale's keys stay labelled do re mi fa sol la ti do, and melodies never leave that octave. The first note is lit ("starts on mi").
- **Wrong notes don't reset.** A wrong note replays the melody, and the notes you already got still count. After two misses, only the next key lights up.
- **Plain-language intro.** It says exactly what you'll hear (single notes, no chords) and what to do.

### Interface
- Key labels on the keyboard picture use the key's full width ("do", "sol"), not just the first letter.

## 0.8.0 — 2026-11-27

Response to the v0.7 session: some notes were very faint, the synth piano sounded toy-like, the band lane was still ahead of the sound, and the scale-degree exercise gave no anchor.

### Sound
- **Real sampled grand piano (optional).** `mfl get-piano` downloads the FreePats YDP Grand Piano: Zenph Studios Yamaha Disklavier Pro samples, 36 MB, CC-BY 3.0. The download is checked against a SHA-256 hash and only the `.sf2` file is extracted. The piano becomes your keyboard sound. A small built-in SoundFont 2 reader adds no dependencies. The synthesized piano is now called "Synth piano".
- **Faint notes fixed.** The Launchkey Mini often sends low velocities. The old curve put a velocity-30 note 19 dB below full; a new floor keeps the softest touch about 11 dB down.

### Band exercises
- **Sound check v2.** Nothing on screen moves with the clicks any more. v1's progress dots advanced at the *scheduled* times, so eyes could lead the taps and the check measured the screen rather than your ears. Clicks are slower (1 per second), and delays up to 0.8 s are measured correctly; v1 could confuse a long delay with a short one. Uneven tapping is retried, and earlier checks are redone automatically.
- **Manual nudge.** In a band exercise, `.` moves the lane later and `,` moves it earlier, in 20 ms steps (remembered).

### Ear training
- **Scale degrees start from an anchor.** First you hear the cadence and play home (do) on the highlighted key. New sets then introduce each note: hear home, then the note, play the highlighted key, and see what the note does ("mi: the bright middle of the home chord"). Only then the quiz, where every round plays home before the mystery note and the possible answers are marked on the keyboard. Wrong keys while being introduced to a note cost nothing.

### Development
- `tests/conftest.py` points data and cache folders at a temporary directory, so tests never read the owner's files or downloaded sounds.

## 0.7.0 — 2026-11-27

Response to the v0.6 session: the sound was still muddy, the band exercises' moving lane was out of step with the sound, the first chord came too suddenly, and the intros needed a sentence of why. Also requested: an accordion.

### Sound
- **A brighter piano.** The additive piano was far too dark: middle C had a spectral centroid of 290–370 Hz (barely above the note itself, 262 Hz) and almost nothing above 2 kHz. Retuned partial roll-off and high-partial decay put it at about 510 Hz (soft) to 820 Hz (hard), with real energy above 2 kHz. The sample cache moves to `samples-v6`, and the first launch re-renders in the background, starting with your current sound.
- **Audio buffer safeguards.** The buffer can't be set below 30 ms any more (a saved 10 ms buffer was crackling). If dropouts still happen, MFL enlarges the buffer by half on the fly and remembers it. The status line shows the buffer size.
- **New sound: Accordion (musette).** Three free reeds beating against each other, with a nasal reed spectrum and a bellows swell. Press `I` to cycle sounds: piano → electric piano → accordion → organ → pad.

### Band exercises
- **Sound check.** A 15-second tap-along to clicks measures when you actually hear the sound (speakers and PipeWire add delay the software can't see). The moving lane is drawn at that offset, so the screen lines up with your ears, and timing is judged against it. It runs before the first band exercise, and again whenever the audio buffer changes. `mfl --resync` repeats it.
- **Two-bar count-in.** Slow clicks first, then every beat, with a big 1 2 3 4 on screen and the first chord named ("first chord: C"). The band starts a second after you press a key.

### Teaching
- **Intro cards say why.** Chords: where they live ("F is IV in C major (subdominant), I in F major (home)…") and how they sound. Progressions: the idiom, its chords in this key with their numbers, and the scale they come from. Grooves: what the rhythm is. Ear exercises: why the skill matters.

## 0.6.0 — 2026-11-27

More hand-holding, cleaner sound. Response to the first real v0.5 session: the sound was distorted and choppy, the volume didn't seem to go up, the instructions were cryptic, and exercises moved on without the learner.

### Sound
- Fixed the distorted "torn speaker" sound. v0.5's make-up gain (3.2×) kept the limiter pulling about 6 dB on every block of ordinary playing, and a tanh saturator ran on everything. The gain is now 1.6× with a smooth limiter that only catches peaks, and a soft knee above 0.8 of full scale replaces the always-on saturation. Reverb return is slightly lower.
- Fixed choppy audio. v0.5 asked PortAudio for 256-frame callbacks at its lowest latency, about a 6 ms deadline that the Python callback missed whenever the screen redrew. Measured on Omarchy with UI-like load: 71 dropouts in 4 s before, none after. The buffer is now 45 ms with host-chosen callback sizes. `mfl --latency 0.08` raises it (remembered), and the status line counts dropouts if any occur.
- Previously rendered samples load at startup, so early notes are no longer pitch-shifted from a distant sample.
- Volume (`+`/`-`) now goes up to 200% and audibly changes loudness. It starts at 100% under a new setting, because v0.5's value doesn't carry over.

### Teaching and pacing
- Every new kind of exercise opens with an intro card: what it is and numbered steps in plain words. It waits until you play any key.
- New chords are taught first (listen → copy the highlighted keys → play from memory). The 6-second "know it?" probe is gone, and nothing changes phase on a timer.
- Play-along waits for you. If you play nothing during your turn, the band stops, nothing is graded, and it starts again when you play a key.
- Tempo control everywhere: `[` and `]` scale every play-along tempo in 5% steps (60–140%, default 85%, remembered). A running play-along restarts at the new tempo.
- `B` (or Backspace) goes back one step and shows its explanation again. `R` repeats the current exercise, or the one just finished while its result is on screen.
- At most three weighted new items per day (was five).

### Interface
- The "what to do now" line sits directly under the chord, marked ▶. Intro text is shown at full brightness.
- The footer shows Hint, Repeat, Back, Skip, Vol−/Vol+, Slower/Faster, Sound and Quit. The status line shows volume and tempo with their keys.

## 0.5.0 — 2026-11-27

A rebuild from a single fixed lesson into a daily, adaptive coach.

### Practice
- Daily plan of about 30 minutes (Warm-up, Learn, Navigate, Ear) followed by open-ended free play. The plan is built from your history, with no choices needed. Sessions resume the same day after quitting.
- Spaced repetition (SM-2 style, four grades derived from performance) across 108 skills in 21 units. Failed items return later in the same session.
- New exercises:
  - chord probe → teach → recall;
  - progression walks with voice-leading guides that follow what you actually played;
  - timed play-along with drums and bass, with per-hit timing and harmony scoring and automatic latency calibration;
  - fading charts (symbols → Roman numerals → none);
  - comping rhythms (ballad, tresillo, habanera, cinquillo, pop eighths, arpeggio, waltz);
  - scale-degree ear training with stepwise resolution;
  - melodic echo;
  - chords by ear;
  - free play with chord naming, key estimation and drum grooves.
- Seasoned chords are sometimes asked by function ("vi in F") to link chords to keys.

### Theory library
- Spelled notes and intervals, 19 scales and modes, 36 chord qualities with aliases and slash chords, and chord identification from MIDI.
- Keys, signatures, Roman numerals with secondary dominants, borrowed chords, slash basses, and harmonic analysis and function descriptions.
- Voice leading, 18 idiomatic progressions, comping patterns and grooves, and Krumhansl–Kessler key estimation.

### Sound
- New engine:
  - sample-accurate scheduler on a shared wall clock;
  - grand piano, electric piano, drawbar organ and warm pad, plus band bass, a synthesized drum kit and metronome;
  - stereo convolution reverb, chorus, tremolo, rotary effect and a peak limiter.
- About 10 dB louder than v0.4 at the same playing strength.
- Fixed the double sound after a blind recall: demonstrations wait for a clear gap after the learner releases all keys, and any new note cancels them.
- Sustain pedal support. Launchkey drum pads (channel 10) trigger drums and are ignored by exercises.
- Rendered samples are cached on disk. The audio device opens in the background so the screen appears instantly.

### Interface
- Redesigned Textual UI: block timeline, large pixel-font chord symbols, a full-colour piano with right and wrong notes, a rhythm lane with a moving cursor, a chord chart, degree chips and a progress screen (keys around the circle of fifths, curriculum path, recent results).
- Instrument, volume and theme are remembered.
- MIDI timestamps are taken in rtmidi's callback. The keyboard can be connected after launch.
- New commands: `plan`, `stats`, `sounds`, `version`. Existing commands and options are unchanged, and `--minutes` is new.

### Data
- Schema version 1: skills, results, sessions and settings tables. The v0.4 `attempts` table is preserved, and previously recalled chords seed skill state.

## 0.4.0
- Audible guidance with a local synth, velocity-sensitive playing sound, and an octave-aware keyboard.

## 0.3.0
- Guided practice without intermediate clicks. Recall with guidance recovery.
