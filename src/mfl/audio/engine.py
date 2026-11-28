"""Real-time mixer: sample and wavetable voices, a scheduler, effects buses,
convolution reverb and a peak limiter.

All public methods are thread-safe. They enqueue commands that the audio
thread applies at the start of the next buffer. Scheduled events use wall
clock seconds from ``time.perf_counter()``. The engine maps them to sample
frames using the device's reported output time, so clicks, backing tracks and
the learner's MIDI timestamps share one clock.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import itertools
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import threading
import time

import numpy as np

from mfl.audio.instruments import Instrument, WavetableInstrument, build_instruments, hz

RENDER_VERSION = 6
FAST_RELEASE = 0.05
# Make-up gain ahead of the limiter. v0.5 used 3.2, which kept the limiter
# pulling ~6 dB on every block of ordinary playing, plus constant tanh
# saturation: audible as a distorted, "torn speaker" sound. At 1.6 a loud
# pedalled four-note chord peaks just under full scale at volume 100%, so the
# limiter only catches extremes. Volume can go to 200% for small speakers.
MASTER_GAIN = 1.6
MAX_VOLUME = 2.0
KNEE = 0.8  # the output stays linear below this level


def velocity_gain(velocity: int) -> float:
    """Loudness for a MIDI velocity. Small keyboards like the Launchkey Mini
    send low velocities for ordinary touches; v0.7's (v/127)^1.5 made a
    velocity-30 note 19 dB below full and some notes nearly vanished. A floor
    keeps the softest touch about 12 dB down while preserving dynamics."""
    v = max(1, min(127, velocity)) / 127
    return 0.25 + 0.75 * v ** 1.6


@dataclass(frozen=True)
class NoteEvent:
    """A note to schedule: wall time, MIDI note, velocity, seconds held."""

    time: float
    note: int
    velocity: int = 80
    duration: float = 0.5
    instrument: str = "keys"  # "keys" follows the selected keyboard sound


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "mfl" / f"samples-v{RENDER_VERSION}"


class SampleBank:
    """Rendered root samples for one instrument, filled by a background thread."""

    def __init__(self, instrument: Instrument, rate: int, disk: Path | None):
        self.instrument = instrument
        self.rate = rate
        self.disk = disk
        self.samples: dict[tuple[int, int], np.ndarray] = {}
        self.roots = instrument.roots()

    def _path(self, root: int, layer: int) -> Path | None:
        if self.disk is None:
            return None
        return self.disk / f"{self.instrument.key}-{self.rate}-{root}-{layer}.npy"

    def ensure(self, root: int, layer: int):
        if (root, layer) in self.samples:
            return
        path = self._path(root, layer)
        data = None
        if path is not None and path.exists():
            try:
                data = np.load(path).astype(np.float32)
            except Exception:
                data = None
        if data is None:
            data = self.instrument.render(root, layer, self.rate).astype(np.float32)
            if path is not None:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".tmp.npy")
                    np.save(tmp, data.astype(np.float16))
                    tmp.replace(path)
                except OSError:
                    pass
        self.samples[(root, layer)] = data

    def load_cached(self):
        """Load every sample already on disk (fast), rendering nothing."""
        for root in self.roots:
            for layer in self.instrument.layers:
                if (root, layer) in self.samples:
                    continue
                path = self._path(root, layer)
                if path is not None and path.exists():
                    try:
                        self.samples[(root, layer)] = np.load(path).astype(np.float32)
                    except Exception:
                        pass

    def warm(self, center: int = 62, stop: threading.Event | None = None):
        order = sorted(self.roots, key=lambda r: abs(r - center))
        for root in order:
            for layer in self.instrument.layers:
                if stop is not None and stop.is_set():
                    return
                self.ensure(root, layer)

    def lookup(self, note: int, layer: int) -> tuple[np.ndarray, float] | None:
        """Nearest rendered sample for a note and the playback ratio."""
        if not self.instrument.pitched:
            sample = self.samples.get((note, layer))
            return (sample, 1.0) if sample is not None else None
        best = None
        for (root, lay), sample in self.samples.items():
            if lay != layer:
                continue
            distance = abs(note - root)
            if best is None or distance < best[0]:
                best = (distance, root, sample)
        if best is None:
            return None
        _, root, sample = best
        return sample, 2 ** ((note - root) / 12)


class Voice:
    """Base voice: mono output, pan gains, optional delayed start and release."""

    __slots__ = ("note", "source", "tag", "bus", "send", "left", "right", "delay", "releasing",
                 "release_left", "release_total", "done", "release_seconds", "event_id")

    def __init__(self, note, source, tag, bus, send, pan, delay):
        self.note, self.source, self.tag, self.bus, self.send = note, source, tag, bus, send
        angle = (pan + 1) * np.pi / 4
        self.left, self.right = float(np.cos(angle)), float(np.sin(angle))
        self.delay = delay
        self.releasing = False
        self.release_left = 0
        self.release_total = 1
        self.done = False
        self.release_seconds = 0.2
        self.event_id = None

    def release(self, frames: int):
        frames = max(1, frames)
        if not self.releasing or frames < self.release_left:
            self.releasing = True
            self.release_left = frames
            self.release_total = frames

    def _release_env(self, n: int) -> np.ndarray | None:
        if not self.releasing:
            return None
        remaining = self.release_left - np.arange(n, dtype=np.float32)
        env = np.clip(remaining / self.release_total, 0, 1) ** 2
        self.release_left -= n
        if self.release_left <= 0:
            self.done = True
        return env

    def render(self, n: int) -> np.ndarray | None:  # pragma: no cover - interface
        raise NotImplementedError


class SampleVoice(Voice):
    __slots__ = ("layers", "ratio", "gain", "pos", "length")

    def __init__(self, layers, ratio, gain, note, source, tag, bus, send, pan, delay):
        super().__init__(note, source, tag, bus, send, pan, delay)
        self.layers = layers  # [(sample, weight)]
        self.ratio = ratio
        self.gain = gain
        self.pos = 0.0
        self.length = min(len(s) for s, _ in layers)

    def render(self, n: int) -> np.ndarray | None:
        out = np.zeros(n, dtype=np.float32)
        start = min(self.delay, n)
        self.delay -= start
        count = n - start
        if count <= 0:
            return out
        positions = self.pos + self.ratio * np.arange(count, dtype=np.float64)
        valid = positions < self.length - 1
        if not valid.any():
            self.done = True
            return out
        positions = positions[valid]
        index = positions.astype(np.int64)
        frac = (positions - index).astype(np.float32)
        block = np.zeros(len(index), dtype=np.float32)
        for sample, weight in self.layers:
            a = sample[index]
            block += weight * (a + (sample[index + 1] - a) * frac)
        self.pos += self.ratio * count
        out[start:start + len(block)] = block * self.gain
        if len(block) < count:
            self.done = True
        env = self._release_env(n)
        if env is not None:
            out *= env
        return out


class OscVoice(Voice):
    """Wavetable oscillator with detuned unison, ADSR and an attack transient."""

    __slots__ = ("table", "incs", "phases", "gain", "age", "attack", "decay", "sustain", "transient", "rate")

    def __init__(self, table, freqs, rate, gain, instrument: WavetableInstrument, transient,
                 note, source, tag, bus, send, pan, delay):
        super().__init__(note, source, tag, bus, send, pan, delay)
        size = len(table)
        self.table = np.append(table, table[0])
        self.incs = [f * instrument.cycle_ratio * size / rate for f in freqs]
        rng = np.random.default_rng(note)
        self.phases = [float(rng.uniform(0, size)) for _ in freqs]
        self.gain = gain / np.sqrt(len(freqs))
        self.age = 0
        self.rate = rate
        self.attack = max(1, int(instrument.attack * rate))
        self.decay = max(1, int(instrument.decay * rate)) if instrument.decay else 0
        self.sustain = instrument.sustain_level
        self.transient = transient

    def render(self, n: int) -> np.ndarray | None:
        out = np.zeros(n, dtype=np.float32)
        start = min(self.delay, n)
        self.delay -= start
        count = n - start
        if count <= 0:
            return out
        size = len(self.table) - 1
        block = np.zeros(count, dtype=np.float32)
        steps = np.arange(count, dtype=np.float64)
        for i, inc in enumerate(self.incs):
            positions = (self.phases[i] + inc * steps) % size
            index = positions.astype(np.int64)
            frac = (positions - index).astype(np.float32)
            a = self.table[index]
            block += a + (self.table[index + 1] - a) * frac
            self.phases[i] = (self.phases[i] + inc * count) % size
        ages = self.age + np.arange(count, dtype=np.float32)
        env = np.minimum(ages / self.attack, 1.0)
        if self.decay:
            env *= np.where(ages < self.attack, 1.0,
                            self.sustain + (1 - self.sustain) * np.exp(-(ages - self.attack) / self.decay))
        block *= env
        if self.transient is not None and self.age < len(self.transient):
            piece = self.transient[self.age:self.age + count]
            block[:len(piece)] += piece
        self.age += count
        out[start:] = block * self.gain
        env_release = self._release_env(n)
        if env_release is not None:
            out *= env_release
        return out


class DelayLine:
    def __init__(self, size: int = 8192):
        self.buffer = np.zeros(size, dtype=np.float32)
        self.size = size
        self.write = 0

    def process(self, x: np.ndarray, delays: np.ndarray) -> np.ndarray:
        n = len(x)
        idx = (self.write + np.arange(n)) % self.size
        self.buffer[idx] = x
        read = (self.write + np.arange(n) - delays) % self.size
        i0 = np.floor(read).astype(np.int64)
        frac = (read - i0).astype(np.float32)
        a = self.buffer[i0 % self.size]
        b = self.buffer[(i0 + 1) % self.size]
        self.write = (self.write + n) % self.size
        return a + (b - a) * frac


class ConvolutionReverb:
    """Uniformly partitioned FFT convolution with a synthetic stereo hall."""

    def __init__(self, rate: int, block: int, seconds: float = 1.7, seed: int = 11):
        self.block = block
        rng = np.random.default_rng(seed)
        n = int(seconds * rate)
        t = np.arange(n) / rate
        freqs = np.fft.rfftfreq(n, 1 / rate)
        channels = []
        for _ in range(2):
            ir = np.zeros(n)
            for low, high, tau in ((0, 400, 0.42), (400, 2500, 0.34), (2500, 7000, 0.2), (7000, rate / 2, 0.1)):
                spectrum = np.fft.rfft(rng.standard_normal(n))
                spectrum[(freqs < low) | (freqs >= high)] = 0
                ir += np.fft.irfft(spectrum, n) * np.exp(-t / tau)
            ir *= np.minimum(t / 0.012, 1)  # pre-delay softening
            for delay, gain in ((0.011, 0.5), (0.019, 0.35), (0.027, 0.3), (0.041, 0.22)):
                ir[int(delay * rate * rng.uniform(0.9, 1.1))] += gain * rng.choice((-1, 1))
            channels.append(ir)
        ir = np.array(channels)
        ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True)) + 1e-9
        parts = int(np.ceil(n / block))
        padded = np.zeros((2, parts * block))
        padded[:, :n] = ir
        segments = padded.reshape(2, parts, block)
        self.spectra = np.fft.rfft(segments, 2 * block, axis=2).astype(np.complex64)
        self.fdl = np.zeros((parts, block + 1), dtype=np.complex64)
        self.head = 0
        self.parts = parts
        self.previous = np.zeros(block, dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        frame = np.concatenate((self.previous, x))
        self.previous = x.copy()
        self.head = (self.head - 1) % self.parts
        self.fdl[self.head] = np.fft.rfft(frame).astype(np.complex64)
        order = (self.head + np.arange(self.parts)) % self.parts
        spectrum = np.einsum("pb,cpb->cb", self.fdl[order], self.spectra)
        return np.fft.irfft(spectrum, 2 * self.block, axis=1)[:, self.block:].astype(np.float32)


class Engine:
    """The software band: the learner's keyboard sound, demonstrations, bass,
    drums and metronome, mixed into one stereo stream."""

    def __init__(self, rate: int = 48000, block: int = 256, *, disk_cache: bool = True, warm: bool = True,
                 instrument: str = "piano", volume: float = 1.0):
        self.rate = rate
        self.block = block
        self.instruments = build_instruments()
        disk = cache_dir() if disk_cache else None
        self.banks = {key: SampleBank(inst, rate, disk) for key, inst in self.instruments.items()
                      if not isinstance(inst, WavetableInstrument)}
        self.tables: dict[tuple[str, int], np.ndarray] = {}
        self.commands: SimpleQueue = SimpleQueue()
        self.events: list = []
        self.sequence = itertools.count()
        self.voices: list[Voice] = []
        self.keys_instrument = instrument if instrument in self.instruments else "piano"
        self.volume = volume
        self.frame = 0
        self.out_frame = 0
        self.offset = time.perf_counter()  # wall time of frame 0, refined by the device clock
        self.synced = False
        self.sustain = False
        self.sustained: set[int] = set()
        self.held_live: set[int] = set()
        self.fifo = np.zeros((0, 2), dtype=np.float32)
        self.reverb = ConvolutionReverb(rate, block)
        self.delays = {name: (DelayLine(), DelayLine()) for name in ("chorus", "leslie")}
        self.tails = {"chorus": 0, "leslie": 0}
        self.lfo_time = 0.0
        self.limiter = 1.0
        self.peak = 0.0
        self._stop = threading.Event()
        self._warm_thread: threading.Thread | None = None
        # Samples cached by an earlier run load in well under a second. Without
        # them a note would be pitch-shifted from a distant root until the
        # background render reaches it, which sounds dull and warbly.
        for bank in self.banks.values():
            bank.load_cached()
        # Make the central piano range available immediately.
        for root in (60,):
            for layer in self.instruments["piano"].layers:
                self.banks["piano"].ensure(root, layer)
        if warm:
            self._warm_thread = threading.Thread(target=self._warm, daemon=True, name="mfl-samples")
            self._warm_thread.start()

    # ---- background preparation -------------------------------------------------
    def _warm(self):
        # The learner's own sound first: it is what they hear on the first key.
        order = [self.keys_instrument, "drums", "bass", "grand", "piano", "epiano"]
        seen = set()
        for key in order:
            if key in seen or key not in self.banks:
                continue
            seen.add(key)
            self.banks[key].warm(stop=self._stop)
        for key, inst in self.instruments.items():
            if isinstance(inst, WavetableInstrument):
                for note in range(21, 109):
                    self._table(key, note)

    def warm_all(self):
        """Render everything synchronously (tests and the ``sounds`` command)."""
        self._warm()

    def _table(self, key: str, note: int) -> np.ndarray:
        table = self.tables.get((key, note))
        if table is None:
            table = self.instruments[key].table(note, self.rate)
            self.tables[(key, note)] = table
        return table

    # ---- thread-safe control API --------------------------------------------------
    def note_on(self, note: int, velocity: int, source: str = "live", instrument: str = "keys"):
        self.commands.put(("on", (note, velocity, source, instrument, None, None)))

    def note_off(self, note: int, source: str = "live"):
        self.commands.put(("off", (note, source)))

    def pedal(self, down: bool):
        self.commands.put(("pedal", down))

    def play(self, events, tag: str = "demo", source: str | None = None):
        """Schedule NoteEvents (wall-clock times)."""
        self.commands.put(("play", (tuple(events), tag, source or tag)))

    def stop(self, tag: str):
        self.commands.put(("stop", tag))

    def set_instrument(self, key: str):
        if key in self.instruments:
            self.keys_instrument = key
            if key in self.banks:
                threading.Thread(target=self.banks[key].warm, daemon=True).start()

    def set_volume(self, volume: float):
        self.volume = float(np.clip(volume, 0.0, MAX_VOLUME))

    def close(self):
        self._stop.set()

    def frame_for(self, wall: float) -> int:
        return int(round((wall - self.offset) * self.rate))

    def wall_for(self, frame: int) -> float:
        return self.offset + frame / self.rate

    # ---- audio thread -------------------------------------------------------------------
    def _apply_commands(self):
        while True:
            try:
                action, args = self.commands.get_nowait()
            except Empty:
                return
            if action == "on":
                note, velocity, source, instrument, _, tag = args
                if source == "live":
                    self.held_live.add(note)
                    self.sustained.discard(note)
                    # The learner always wins: a demonstration yields immediately.
                    self._release_where(lambda v: v.source == "demo", FAST_RELEASE)
                    self._drop_events(lambda e: e[3][2] == "demo")
                self._start(note, velocity, source, instrument, tag, 0)
            elif action == "off":
                note, source = args
                if source == "live":
                    self.held_live.discard(note)
                    if self.sustain:
                        self.sustained.add(note)
                        continue
                self._release_note(note, source)
            elif action == "pedal":
                self.sustain = bool(args)
                if not self.sustain:
                    for note in list(self.sustained):
                        if note not in self.held_live:
                            self._release_note(note, "live")
                    self.sustained.clear()
            elif action == "play":
                events, tag, source = args
                for event in events:
                    start = max(self.frame, self.frame_for(event.time))
                    end = max(start + 1, self.frame_for(event.time + event.duration))
                    event_id = next(self.sequence)
                    heapq.heappush(self.events, (start, event_id, "on", (event, tag, source, event_id)))
                    if event.instrument != "drums":
                        heapq.heappush(self.events, (end, next(self.sequence), "off", (event, tag, source, event_id)))
            elif action == "stop":
                tag = args
                self._drop_events(lambda e: e[3][1] == tag)
                self._release_where(lambda v: v.tag == tag, FAST_RELEASE)

    def _drop_events(self, predicate):
        kept = [e for e in self.events if not predicate(e)]
        if len(kept) != len(self.events):
            self.events = kept
            heapq.heapify(self.events)

    def _release_where(self, predicate, seconds: float):
        for voice in self.voices:
            if predicate(voice):
                voice.release(int(seconds * self.rate))

    def _release_note(self, note: int, source: str):
        for voice in self.voices:
            if voice.note == note and voice.source == source and not voice.releasing:
                voice.release(int(voice.release_seconds * self.rate))

    def _start(self, note: int, velocity: int, source: str, instrument: str, tag, delay: int,
               event_id: int | None = None):
        key = self.keys_instrument if instrument == "keys" else instrument
        inst = self.instruments.get(key)
        if inst is None:
            return
        # Retriggering a note releases its previous voice from the same source.
        for voice in self.voices:
            if voice.note == note and voice.source == source and inst.pitched:
                voice.release(int(0.03 * self.rate))
        velocity = int(np.clip(velocity, 1, 127))
        gain = inst.gain * velocity_gain(velocity) * (0.55 if source == "demo" else 1.0) + 1e-4
        pan = float(np.clip((note - 64) / 70, -0.45, 0.45)) if inst.pitched else 0.0
        if isinstance(inst, WavetableInstrument):
            table = self._table(key, note)
            base = hz(note)
            freqs = [base * 2 ** (c / 1200) for c in inst.detune_cents]
            transient = inst.transient(note, 1, self.rate)
            voice: Voice = OscVoice(table, freqs, self.rate, gain, inst, transient,
                                    note, source, tag, inst.bus, inst.reverb_send, pan, delay)
        else:
            bank = self.banks[key]
            soft_hard = float(np.clip((velocity - 35) / 75, 0, 1))
            layers = []
            if len(inst.layers) == 1:
                found = bank.lookup(note, inst.layers[0])
                if found is None:
                    return
                layers, ratio = [(found[0], 1.0)], found[1]
            else:
                soft = bank.lookup(note, 0)
                hard = bank.lookup(note, 1)
                if soft is None or hard is None:
                    return
                ratio = soft[1]
                if hard[1] != ratio:  # different roots rendered so far; use one layer
                    layers = [(hard[0] if soft_hard > 0.5 else soft[0], 1.0)]
                    ratio = hard[1] if soft_hard > 0.5 else soft[1]
                else:
                    layers = [(soft[0], 1 - soft_hard), (hard[0], soft_hard)]
            voice = SampleVoice(layers, ratio, gain, note, source, tag, inst.bus, inst.reverb_send, pan, delay)
        voice.release_seconds = inst.release if inst.pitched else 5.0  # drums ring out
        voice.event_id = event_id
        self.voices.append(voice)
        if len(self.voices) > 72:
            for old in self.voices[:len(self.voices) - 64]:
                old.release(int(0.02 * self.rate))

    def _run_events(self, block_end: int):
        while self.events and self.events[0][0] < block_end:
            frame, _, kind, (event, tag, source, event_id) = heapq.heappop(self.events)
            delay = max(0, frame - self.frame)
            if kind == "on":
                self._start(event.note, event.velocity, source, event.instrument, tag, delay, event_id)
            else:
                for voice in self.voices:
                    if voice.event_id == event_id and not voice.releasing:
                        voice.release(int(voice.release_seconds * self.rate))

    def _render_block(self) -> np.ndarray:
        n = self.block
        self._run_events(self.frame + n)
        buses = {name: np.zeros((2, n), dtype=np.float32) for name in ("dry", "chorus", "tremolo", "leslie")}
        send = np.zeros(n, dtype=np.float32)
        alive = []
        for voice in self.voices:
            mono = voice.render(n)
            if mono is not None:
                bus = buses[voice.bus]
                bus[0] += mono * voice.left
                bus[1] += mono * voice.right
                if voice.send:
                    send += mono * voice.send
            if not voice.done:
                alive.append(voice)
        self.voices = alive
        t = self.lfo_time + np.arange(n) / self.rate
        self.lfo_time += n / self.rate
        mix = buses["dry"]
        trem = buses["tremolo"]
        if trem.any():
            pan = (0.5 + 0.5 * np.sin(2 * np.pi * 4.2 * t)).astype(np.float32)
            mix[0] += trem[0] * (1 - 0.5 * pan)
            mix[1] += trem[1] * (0.5 + 0.5 * pan)
        for name, rate, depth, base, wet in (("chorus", 0.35, 0.004, 0.016, 0.55), ("leslie", 6.2, 0.0007, 0.003, 0.6)):
            bus = buses[name]
            self.tails[name] = 16 if bus.any() else self.tails[name] - 1
            if self.tails[name] <= 0:
                continue
            mono = bus.mean(axis=0)
            delay_left = (base + depth * np.sin(2 * np.pi * rate * t)) * self.rate
            delay_right = (base + depth * np.cos(2 * np.pi * rate * t)) * self.rate
            left = self.delays[name][0].process(mono, delay_left)
            right = self.delays[name][1].process(mono, delay_right)
            mix[0] += bus[0] * (1 - wet * 0.5) + wet * left
            mix[1] += bus[1] * (1 - wet * 0.5) + wet * right
        if send.any() or self.reverb.fdl.any():
            mix += 0.4 * self.reverb.process(send)
        mix *= self.volume * MASTER_GAIN
        # Peak limiter: fast attack, smooth ~0.3 s release. It only acts on
        # peaks above full scale, so normal playing passes through untouched.
        peak = float(np.abs(mix).max())
        target = min(1.0, 0.98 / peak) if peak > 0 else 1.0
        if target < self.limiter:
            new_gain = target
        else:
            new_gain = self.limiter + (target - self.limiter) * (1 - np.exp(-n / (0.3 * self.rate)))
        if new_gain != 1.0 or self.limiter != 1.0:
            mix *= np.linspace(self.limiter, new_gain, n, dtype=np.float32)
        self.limiter = float(new_gain)
        # Soft knee: linear below KNEE, then a smooth curve towards 1.0, so the
        # remaining overshoot of the gain ramp never clips hard.
        over = np.abs(mix) > KNEE
        if over.any():
            x = mix[over]
            mix[over] = np.sign(x) * (KNEE + (1 - KNEE) * np.tanh((np.abs(x) - KNEE) / (1 - KNEE)))
        self.peak = max(self.peak * 0.95, float(np.abs(mix).max()))
        self.frame += n
        return mix.T

    def render(self, frames: int, dac_wall: float | None = None) -> np.ndarray:
        """Produce ``frames`` stereo samples; ``dac_wall`` is when the first
        frame reaches the speakers (perf_counter seconds)."""
        if dac_wall is not None:
            measured = dac_wall - self.out_frame / self.rate
            if not self.synced or abs(measured - self.offset) > 0.04:
                self.offset = measured
                self.synced = True
            else:
                self.offset += 0.02 * (measured - self.offset)
        self._apply_commands()
        while len(self.fifo) < frames:
            self.fifo = np.concatenate((self.fifo, self._render_block()))
        out, self.fifo = self.fifo[:frames], self.fifo[frames:]
        self.out_frame += frames
        return out
