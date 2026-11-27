# Changelog

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
