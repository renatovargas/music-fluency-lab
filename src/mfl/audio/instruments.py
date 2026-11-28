"""Offline-rendered and wavetable instruments. Pure NumPy, no sound fonts.

Decaying instruments (piano, electric piano, bass, drums) are rendered once
per root note into sample buffers and pitch-shifted by up to ±1 semitone at
playback, like a multisampled sound library. Sustaining instruments (organ,
pad) run band-limited wavetable oscillators in real time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TILT = (1.25, 0.85)  # partial amplitude ~ k^-tilt for the soft and hard layers
HIGH_DECAY_HZ = 2200.0  # partials above this die away progressively faster
SAMPLE_STEP = 3  # render every minor third, resample the notes in between
LOW_NOTE, HIGH_NOTE = 21, 108


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _attack(n: int, rate: int, seconds: float) -> np.ndarray:
    return np.minimum(np.arange(n, dtype=np.float32) / max(1, int(seconds * rate)), 1.0)


def _fade_tail(buffer: np.ndarray, rate: int, seconds: float = 0.25) -> np.ndarray:
    tail = min(len(buffer), int(seconds * rate))
    buffer[-tail:] *= np.linspace(1, 0, tail, dtype=np.float32) ** 2
    return buffer


def _upsample(x: np.ndarray, factor: int) -> np.ndarray:
    """Band-limited integer upsampling via zero-padded FFT."""
    if factor == 1:
        return x
    spectrum = np.fft.rfft(x)
    n_out = len(x) * factor
    padded = np.zeros(n_out // 2 + 1, dtype=complex)
    padded[: len(spectrum)] = spectrum * factor
    return np.fft.irfft(padded, n_out)


def _lowpassed_noise(n: int, rate: int, rng, cutoff: float) -> np.ndarray:
    noise = rng.standard_normal(n)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / rate)
    spectrum /= 1 + (freqs / cutoff) ** 2
    return np.fft.irfft(spectrum, n)


@dataclass
class Instrument:
    key: str
    name: str
    sustained: bool = False
    release: float = 0.2
    bus: str = "dry"  # "dry", "chorus", "tremolo", "leslie"
    reverb_send: float = 0.25
    gain: float = 1.0
    layers: tuple[int, ...] = (0, 1)  # velocity layers (soft, hard)
    pitched: bool = True

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    def roots(self) -> list[int]:
        return list(range(LOW_NOTE, HIGH_NOTE + 1, SAMPLE_STEP))


class GrandPiano(Instrument):
    """Additive piano: stretched inharmonic partials, two detuned strings,
    frequency-dependent two-stage decay, a hammer-position comb filter and a
    felt thump. Velocity changes brightness as well as level."""

    def __init__(self):
        super().__init__("piano", "Synth piano", release=0.28, reverb_send=0.30, gain=1.0)

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:
        rng = np.random.default_rng(note * 7 + layer)
        f0 = hz(note)
        duration = float(np.clip(7.5 - (note - 21) * 0.075, 1.3, 7.5))
        inharmonicity = 0.00006 * 2 ** ((note - 40) / 14)
        # Spectral tilt and decay were retuned in v0.7: v0.6's piano had a
        # centroid barely above the fundamental (dull, "muddy"). Targets: a
        # mezzo-forte C4 centred near 0.9-1.2 kHz with real energy above 2 kHz.
        tilt = TILT[layer]
        ceiling = min(0.45 * rate, 9000 if layer == 0 else 15000)
        max_partials = 64 if note < 48 else 40
        partials = []
        for k in range(1, max_partials + 1):
            fk = k * f0 * np.sqrt(1 + inharmonicity * k * k)
            if fk > ceiling:
                break
            partials.append((k, fk))
        top = partials[-1][1] if partials else f0
        # Low notes only contain low partials: synthesize at a reduced rate.
        factor = 1
        while factor < 8 and top < 0.4 * rate / (factor * 2):
            factor *= 2
        sub_rate = rate // factor
        n = int(duration * sub_rate)
        t_full = np.arange(n, dtype=np.float64) / sub_rate
        body = np.zeros(n)
        sustain = float(np.clip(6.0 * 2 ** (-(note - 45) / 22), 0.5, 11.0))
        strike = 1 / 7.6
        detune = 0.00035 + 0.0001 * layer
        for k, fk in partials:
            amp = k ** -tilt * (0.3 + 0.7 * abs(np.sin(np.pi * k * strike)))
            if amp < 0.002:
                continue
            tau = sustain / (1 + (fk / HIGH_DECAY_HZ) ** 1.1)
            # Only compute this partial until it has decayed below audibility.
            length = min(n, int(tau * np.log(max(amp * 0.3 / 2e-5, 1.0)) * sub_rate) + 1)
            t = t_full[:length]
            # Prompt sound, then a quieter aftersound with a slower decay.
            env = (0.7 * np.exp(-t / (tau * 0.22)) + 0.3 * np.exp(-t / tau)) * amp
            phase = rng.uniform(0, 2 * np.pi)
            wave = np.sin(2 * np.pi * fk * t + phase)
            if k <= 8:  # second string of the unison, slightly detuned: slow beating
                wave = 0.55 * wave + 0.45 * np.sin(2 * np.pi * fk * (1 + detune) * t + phase * 1.3)
            body[:length] += env * wave
        out = _upsample(body, factor).astype(np.float32)
        n = len(out)
        # Hammer thump: a short filtered noise burst, darker on soft notes.
        thump_n = int(0.03 * rate)
        thump = _lowpassed_noise(thump_n, rate, rng, 900 + 2500 * layer + f0)
        thump *= np.exp(-np.arange(thump_n) / (0.006 * rate))
        out[:thump_n] += (0.05 + 0.06 * layer) * thump.astype(np.float32) / (np.abs(thump).max() + 1e-9)
        out *= _attack(n, rate, 0.0015)
        # Equal loudness across the range, bass a little fuller.
        out /= np.sqrt(np.mean(out[: int(0.25 * rate)] ** 2)) + 1e-9
        out *= 0.17 * (1.0 + 0.25 * (note < 48))
        return _fade_tail(out, rate, 0.4)


class ElectricPiano(Instrument):
    """Two-operator FM tine piano: a mellow body that barks when struck hard,
    plus a short metallic tine transient. Played through stereo tremolo."""

    def __init__(self):
        super().__init__("epiano", "Electric piano", release=0.3, bus="tremolo", reverb_send=0.22, gain=0.85)

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:
        f0 = hz(note)
        duration = float(np.clip(6.0 - (note - 36) * 0.06, 1.2, 6.0))
        n = int(duration * rate)
        t = np.arange(n, dtype=np.float64) / rate
        bark = 0.6 + 1.5 * layer
        index = bark * np.exp(-t / 0.35) * min(1.0, 600 / f0 + 0.35) + 0.2
        body = np.sin(2 * np.pi * f0 * t + index * np.sin(2 * np.pi * f0 * t))
        tine = np.zeros(n)
        if 14 * f0 < 0.4 * rate:
            tine_index = (1.2 + 2.5 * layer) * np.exp(-t / 0.015)
            tine = np.sin(2 * np.pi * f0 * t + tine_index * np.sin(2 * np.pi * 14 * f0 * t)) * np.exp(-t / 0.12)
        tau = float(np.clip(3.4 * 2 ** (-(note - 60) / 26), 0.6, 6.0))
        env = 0.75 * np.exp(-t / tau) + 0.25 * np.exp(-t / (tau * 0.25))
        out = ((0.85 * body + (0.18 + 0.12 * layer) * tine) * env).astype(np.float32)
        out *= _attack(n, rate, 0.002)
        out /= np.sqrt(np.mean(out[: int(0.25 * rate)] ** 2)) + 1e-9
        return _fade_tail(out * 0.16, rate, 0.3)


class Bass(Instrument):
    """Round finger bass for the virtual band."""

    def __init__(self):
        super().__init__("bass", "Bass", release=0.09, reverb_send=0.04, gain=0.62, layers=(1,))

    def roots(self) -> list[int]:
        return list(range(24, 64, SAMPLE_STEP))

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:
        f0 = hz(note)
        n = int(2.6 * rate)
        t = np.arange(n, dtype=np.float32) / rate
        out = np.zeros(n, dtype=np.float32)
        for k in range(1, 16):
            fk = k * f0
            if fk > 0.4 * rate:
                break
            amp = (1 / k) * np.exp(-fk / 520)
            env = np.exp(-t / (1.3 / (1 + fk / 900)))
            out += (amp * env * np.sin(2 * np.pi * fk * t)).astype(np.float32)
        pluck = np.exp(-t / 0.012) * np.sin(2 * np.pi * 3 * f0 * t) * 0.15
        out += pluck.astype(np.float32)
        out *= _attack(n, rate, 0.003)
        out /= np.abs(out).max() + 1e-9
        return _fade_tail(out * 0.42, rate, 0.2)


class Drums(Instrument):
    """Synthesized percussion on General MIDI note numbers."""

    def __init__(self):
        super().__init__("drums", "Drums", release=10.0, reverb_send=0.12, gain=0.62, layers=(1,), pitched=False)

    def roots(self) -> list[int]:
        return [36, 37, 38, 39, 42, 46, 56, 60, 61, 62, 63, 64, 70, 75, 76, 77]

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:
        rng = np.random.default_rng(note)

        def time(seconds):
            n = int(seconds * rate)
            return np.arange(n) / rate

        def noise(t, cutoff):
            x = _lowpassed_noise(len(t), rate, rng, cutoff)
            return x / (np.abs(x).max() + 1e-9)

        if note == 36:  # kick
            t = time(0.5)
            pitch = 48 + 90 * np.exp(-t / 0.035)
            out = np.sin(2 * np.pi * np.cumsum(pitch) / rate) * np.exp(-t / 0.18)
            out += 0.3 * noise(t, 3000) * np.exp(-t / 0.004)
            level = 0.9
        elif note in (38, 39):  # snare, clap
            t = time(0.35)
            tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)
            body = noise(t, 7000) * np.exp(-t / (0.09 if note == 38 else 0.06))
            if note == 39:
                body *= 1 + 0.6 * (np.sin(2 * np.pi * 90 * t) > 0) * (t < 0.03)
            out = 0.45 * tone + body
            level = 0.55
        elif note == 37:  # side stick / rim
            t = time(0.12)
            out = (np.sin(2 * np.pi * 1700 * t) + 0.6 * np.sin(2 * np.pi * 820 * t)) * np.exp(-t / 0.012)
            out += 0.3 * noise(t, 6000) * np.exp(-t / 0.004)
            level = 0.45
        elif note in (42, 46, 70):  # hats and shaker: bright noise
            t = time(0.07 if note == 42 else 0.4 if note == 46 else 0.11)
            raw = np.diff(_lowpassed_noise(len(t) + 1, rate, rng, 16000))
            raw /= np.abs(raw).max() + 1e-9
            if note == 70:
                env = np.minimum(t / 0.02, 1) * np.exp(-t / 0.04)
            else:
                env = np.exp(-t / (0.018 if note == 42 else 0.12))
            out = raw * env
            level = 0.28 if note != 70 else 0.22
        elif note in (60, 61, 62, 63, 64):  # bongos and congas
            base = {60: 420, 61: 300, 62: 330, 63: 220, 64: 250}[note]
            t = time(0.4)
            f = base * (1 + 0.25 * np.exp(-t / 0.01))
            out = np.sin(2 * np.pi * np.cumsum(f) / rate) * np.exp(-t / (0.07 if note < 62 else 0.12))
            out += 0.15 * noise(t, 4000) * np.exp(-t / 0.003)
            level = 0.45
        elif note == 75:  # claves
            t = time(0.15)
            out = np.sin(2 * np.pi * 2500 * t) * np.exp(-t / 0.03)
            level = 0.35
        elif note == 56:  # cowbell
            t = time(0.3)
            out = (np.sign(np.sin(2 * np.pi * 540 * t)) + np.sign(np.sin(2 * np.pi * 800 * t))) * np.exp(-t / 0.07)
            out = np.diff(out, prepend=0) * 0.5 + out * 0.2
            level = 0.15
        else:  # 76/77 metronome woodblock clicks
            t = time(0.06)
            f = 2000 if note == 76 else 1350
            out = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.7 * t)) * np.exp(-t / 0.009)
            level = 1.0
        out = out / (np.abs(out).max() + 1e-9) * level
        return out.astype(np.float32)


class WavetableInstrument(Instrument):
    """Sustained oscillator voice. One table cycle lasts two periods of the
    note (``cycle_ratio`` 0.5), so sub-octave partials fit exactly."""

    size = 4096
    cycle_ratio = 0.5
    detune_cents: tuple[float, ...] = (0.0,)
    attack = 0.005
    decay = 0.0
    sustain_level = 1.0

    def harmonics(self, note: int, rate: int) -> list[tuple[int, float]]:
        """(multiple of the cycle frequency, amplitude) pairs."""
        raise NotImplementedError

    def table(self, note: int, rate: int) -> np.ndarray:
        phase = np.arange(self.size) / self.size
        out = np.zeros(self.size)
        cycle_hz = hz(note) * self.cycle_ratio
        for multiple, amp in self.harmonics(note, rate):
            if multiple * cycle_hz < 0.45 * rate:
                out += amp * np.sin(2 * np.pi * multiple * phase)
        peak = np.abs(out).max() or 1.0
        return (out / peak).astype(np.float32)

    def transient(self, note: int, layer: int, rate: int) -> np.ndarray | None:
        return None


class Organ(WavetableInstrument):
    """Drawbar organ: sub-octave, unison, fifth and octave pipes, with key
    click and decaying second-harmonic percussion. Plays through a rotary
    speaker style chorus."""

    def __init__(self):
        super().__init__("organ", "Drawbar organ", sustained=True, release=0.06, bus="leslie",
                         reverb_send=0.18, gain=0.24, layers=(1,))

    def harmonics(self, note, rate):
        # Table cycle = the 16' sub-octave, so multiples are footages × 2.
        return [(1, 0.55), (2, 1.0), (3, 0.55), (4, 0.7), (6, 0.25), (8, 0.35), (16, 0.12)]

    def transient(self, note, layer, rate):
        n = int(0.5 * rate)
        t = np.arange(n) / rate
        f0 = hz(note)
        perc = 0.35 * np.sin(2 * np.pi * 3 * f0 * t) * np.exp(-t / 0.16) if 3 * f0 < 0.45 * rate else 0 * t
        click = np.random.default_rng(note).standard_normal(n) * np.exp(-t / 0.0015) * 0.12
        return (perc + click).astype(np.float32)


class Pad(WavetableInstrument):
    """Warm analog-style pad: three detuned, gently filtered saws and a sub,
    slow attack and long release, widened by chorus."""

    detune_cents = (-9.0, 0.0, 8.0)
    attack = 0.35
    decay = 0.8
    sustain_level = 0.8

    def __init__(self):
        super().__init__("pad", "Warm pad", sustained=True, release=1.3, bus="chorus",
                         reverb_send=0.45, gain=0.17, layers=(1,))

    def harmonics(self, note, rate):
        f0 = hz(note)
        cutoff = 1400 + 900 * (note > 72)
        saw = [(2 * k, (1 / k) * float(np.exp(-k * f0 / cutoff))) for k in range(1, 48)]
        return saw + [(1, 0.3)] if note > 52 else saw


class Accordion(WavetableInstrument):
    """Musette accordion: three free reeds per note, one in tune and two
    detuned either side, which beat against each other for the shimmering
    sound of Latin, norteño and French accordion. A reed's spectrum is rich
    and nasal (strong harmonics with a formant around 1–2 kHz). The bellows
    give a soft, quick swell instead of a struck attack."""

    detune_cents = (-13.0, 0.0, 12.0)
    attack = 0.035
    decay = 0.6
    sustain_level = 0.88

    def __init__(self):
        super().__init__("accordion", "Accordion (musette)", sustained=True, release=0.07, bus="dry",
                         reverb_send=0.2, gain=0.28, layers=(1,))

    def harmonics(self, note, rate):
        f0 = hz(note)
        result = []
        for k in range(1, 40):
            fk = k * f0
            if fk > 9000:
                break
            formant = 1 + 1.4 * float(np.exp(-((np.log2(fk / 1400)) ** 2) / 0.5))
            odd = 1.0 if k % 2 else 0.7  # reeds are a little stronger on odd partials
            result.append((2 * k, k ** -0.85 * formant * odd))
        return result

    def transient(self, note, layer, rate):
        # A breath of reed noise as the bellows open.
        n = int(0.04 * rate)
        t = np.arange(n) / rate
        noise = _lowpassed_noise(n, rate, np.random.default_rng(note), 3000.0)
        return (0.03 * noise / (np.abs(noise).max() + 1e-9) * np.exp(-t / 0.012)).astype(np.float32)


SYNTH_PLAYABLE = ("piano", "epiano", "accordion", "organ", "pad")


def _sampled() -> list[Instrument]:
    from mfl.audio.soundfont import SoundFontPiano, installed_piano

    path = installed_piano()
    return [SoundFontPiano(path)] if path is not None else []


def build_instruments() -> dict[str, Instrument]:
    return {i.key: i for i in (*_sampled(), GrandPiano(), ElectricPiano(), Accordion(), Organ(), Pad(), Bass(),
                               Drums())}


# The sampled grand (after ``mfl get-piano``) comes first when installed.
PLAYABLE = tuple(k for k in ("grand", *SYNTH_PLAYABLE) if k in build_instruments())
