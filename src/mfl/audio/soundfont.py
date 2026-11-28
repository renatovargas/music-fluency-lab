"""A minimal SoundFont 2 reader and an instrument that renders from it.

Only what a sampled piano needs: one preset's zones (key and velocity
ranges), sample data with loops, tuning, attenuation and the volume
envelope. Each root note is rendered offline into a plain sample buffer, so
the real-time engine treats it exactly like the synthesized instruments.

Optional download: ``mfl get-piano`` fetches the FreePats YDP Grand Piano
(Zenph Studios Yamaha Disklavier Pro samples, CC-BY 3.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import struct

import numpy as np

from mfl.audio.instruments import Instrument, _attack, _fade_tail

YDP_URL = "https://freepats.zenvoid.org/Piano/YDP-GrandPiano/YDP-GrandPiano-SF2-20160804.tar.bz2"
YDP_SHA256 = "d243dc3e182a60df2a16e92828c1821cf3eb5748b45e2e2bdcfa9cf7af056026"
YDP_FILE = "YDP-GrandPiano-20160804.sf2"
ATTRIBUTION = ("Grand piano: FreePats YDP Grand Piano by roberto@zenvoid.org, from the Zenph Studios Yamaha "
               "Disklavier Pro Piano Multisamples for OLPC. CC-BY 3.0, "
               "https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html")

# Generator numbers (SoundFont 2.04 §8.1.2).
START_OFS, END_OFS, LOOP_START_OFS, LOOP_END_OFS = 0, 1, 2, 3
START_COARSE, END_COARSE, LOOP_START_COARSE, LOOP_END_COARSE = 4, 12, 45, 50
ATTACK, HOLD, DECAY, SUSTAIN = 34, 35, 36, 37
INSTRUMENT, KEY_RANGE, VEL_RANGE, ATTENUATION = 41, 43, 44, 48
COARSE_TUNE, FINE_TUNE, SAMPLE_ID, SAMPLE_MODES, ROOT_KEY = 51, 52, 53, 54, 58
RANGES = (KEY_RANGE, VEL_RANGE)


def sounds_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mfl" / "sounds"


def installed_piano() -> Path | None:
    path = sounds_dir() / YDP_FILE
    return path if path.exists() else None


@dataclass
class SampleHeader:
    name: str
    start: int
    end: int
    loop_start: int
    loop_end: int
    rate: int
    pitch: int
    correction: int


@dataclass
class Zone:
    gens: dict = field(default_factory=dict)

    def range(self, gen: int) -> tuple[int, int]:
        return self.gens.get(gen, (0, 127))


def _chunks(data: memoryview, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        cid = bytes(data[pos:pos + 4]).decode("latin-1")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        yield cid, pos + 8, size
        pos += 8 + size + (size & 1)


def _records(data, offset, size, fmt):
    step = struct.calcsize(fmt)
    return [struct.unpack_from(fmt, data, offset + i * step) for i in range(size // step)]


class SoundFont:
    def __init__(self, path: Path):
        self.path = Path(path)
        raw = np.memmap(self.path, dtype=np.uint8, mode="r")
        data = memoryview(raw)
        if bytes(data[0:4]) != b"RIFF" or bytes(data[8:12]) != b"sfbk":
            raise ValueError(f"{path} is not a SoundFont 2 file")
        lists = {}
        for cid, offset, size in _chunks(data, 12, len(data)):
            if cid == "LIST":
                lists[bytes(data[offset:offset + 4]).decode("latin-1")] = (offset + 4, offset + size)
        sdta, pdta = lists["sdta"], lists["pdta"]
        self.samples = None
        for cid, offset, size in _chunks(data, *sdta):
            if cid == "smpl":
                self.samples = np.frombuffer(raw, dtype="<i2", count=size // 2, offset=offset)
        hydra = {cid: (offset, size) for cid, offset, size in _chunks(data, *pdta)}
        phdr = _records(data, *hydra["phdr"], "<20sHHHIII")
        pbag = _records(data, *hydra["pbag"], "<HH")
        pgen = _records(data, *hydra["pgen"], "<Hh")
        inst = _records(data, *hydra["inst"], "<20sH")
        ibag = _records(data, *hydra["ibag"], "<HH")
        igen = _records(data, *hydra["igen"], "<Hh")
        shdr = _records(data, *hydra["shdr"], "<20sIIIIIBbHH")
        self.headers = [SampleHeader(n.split(b"\0")[0].decode("latin-1"), s, e, ls, le, r, p, c)
                        for n, s, e, ls, le, r, p, c, _, _ in shdr[:-1]]
        self.presets = [(name.split(b"\0")[0].decode("latin-1"), bank, program, bag)
                        for name, program, bank, bag, *_ in phdr]
        self._pbag, self._pgen, self._inst, self._ibag, self._igen = pbag, pgen, inst, ibag, igen

    @staticmethod
    def _zones(bags, gens, first: int, last: int) -> list[Zone]:
        zones = []
        for b in range(first, last):
            zone = Zone()
            for oper, amount in gens[bags[b][0]:bags[b + 1][0]]:
                if oper in RANGES:
                    lo, hi = struct.unpack("<BB", struct.pack("<h", amount))
                    zone.gens[oper] = (lo, hi)
                else:
                    zone.gens[oper] = amount
            zones.append(zone)
        return zones

    def regions(self, bank: int = 0, program: int = 0) -> list[dict]:
        """Flattened (preset × instrument) zones of one preset: generator
        values with instrument defaults applied and preset offsets added."""
        index = next((i for i, (_, b, p, _) in enumerate(self.presets[:-1]) if (b, p) == (bank, program)), 0)
        pzones = self._zones(self._pbag, self._pgen, self.presets[index][3], self.presets[index + 1][3])
        pglobal = pzones[0].gens if pzones and INSTRUMENT not in pzones[0].gens else {}
        result = []
        for pz in pzones:
            if INSTRUMENT not in pz.gens:
                continue
            i = pz.gens[INSTRUMENT]
            izones = self._zones(self._ibag, self._igen, self._inst[i][1], self._inst[i + 1][1])
            iglobal = izones[0].gens if izones and SAMPLE_ID not in izones[0].gens else {}
            for iz in izones:
                if SAMPLE_ID not in iz.gens:
                    continue
                gens = {**iglobal, **iz.gens}
                pgens = {**pglobal, **pz.gens}
                for gen in (KEY_RANGE, VEL_RANGE):
                    a, b = gens.get(gen, (0, 127)), pgens.get(gen, (0, 127))
                    gens[gen] = (max(a[0], b[0]), min(a[1], b[1]))
                for gen, amount in pgens.items():  # preset generators are offsets
                    if gen in (ATTENUATION, COARSE_TUNE, FINE_TUNE, ATTACK, HOLD, DECAY, SUSTAIN):
                        gens[gen] = gens.get(gen, 0) + amount
                result.append(gens)
        return result

    def region_for(self, regions: list[dict], note: int, velocity: int) -> dict | None:
        candidates = [g for g in regions if g[KEY_RANGE][0] <= note <= g[KEY_RANGE][1]
                      and g[VEL_RANGE][0] <= velocity <= g[VEL_RANGE][1]]
        if not candidates:  # nearest key range at this velocity, then anything
            candidates = sorted(regions, key=lambda g: (
                min(abs(note - g[KEY_RANGE][0]), abs(note - g[KEY_RANGE][1])),
                0 if g[VEL_RANGE][0] <= velocity <= g[VEL_RANGE][1] else 1))[:1]
        return candidates[0] if candidates else None


def _seconds(timecents: int | None, default: float) -> float:
    if timecents is None:
        return default
    return float(2 ** (timecents / 1200))


class SoundFontPiano(Instrument):
    """A sampled piano from an SF2 file, rendered per root note."""

    LAYER_VELOCITY = (52, 112)  # soft and hard layers

    def __init__(self, path: Path, key: str = "grand", name: str = "Grand piano (sampled)"):
        super().__init__(key, name, release=0.3, reverb_send=0.22, gain=1.0)
        self.path = Path(path)
        self._font: SoundFont | None = None
        self._regions: list[dict] | None = None

    def _load(self):
        if self._font is None:
            self._font = SoundFont(self.path)
            self._regions = self._font.regions(0, 0)

    def render(self, note: int, layer: int, rate: int) -> np.ndarray:
        self._load()
        font, regions = self._font, self._regions
        region = font.region_for(regions, note, self.LAYER_VELOCITY[layer])
        if region is None:
            return np.zeros(int(0.1 * rate), dtype=np.float32)
        header = font.headers[region[SAMPLE_ID]]
        start = header.start + region.get(START_OFS, 0) + 32768 * region.get(START_COARSE, 0)
        end = header.end + region.get(END_OFS, 0) + 32768 * region.get(END_COARSE, 0)
        loop_start = header.loop_start + region.get(LOOP_START_OFS, 0) + 32768 * region.get(LOOP_START_COARSE, 0)
        loop_end = header.loop_end + region.get(LOOP_END_OFS, 0) + 32768 * region.get(LOOP_END_COARSE, 0)
        source = font.samples[start:end].astype(np.float32) / 32768.0
        looped = region.get(SAMPLE_MODES, 0) in (1, 3) and start < loop_start < loop_end <= end
        root = region.get(ROOT_KEY, -1)
        root = header.pitch if root is None or root < 0 or root > 127 else root
        cents = 100 * (note - root) + 100 * region.get(COARSE_TUNE, 0) + region.get(FINE_TUNE, 0) + header.correction
        step = 2 ** (cents / 1200) * header.rate / rate
        duration = float(np.clip(9.0 - (note - 21) * 0.08, 1.5, 9.0))
        n = int(duration * rate)
        positions = np.arange(n, dtype=np.float64) * step
        if looped:
            ls, le = loop_start - start, loop_end - start
            beyond = positions >= le
            positions[beyond] = ls + np.mod(positions[beyond] - ls, le - ls)
        else:
            positions = positions[positions < len(source) - 1]
        index = positions.astype(np.int64)
        frac = (positions - index).astype(np.float32)
        nxt = np.minimum(index + 1, len(source) - 1)
        out = source[index] + (source[nxt] - source[index]) * frac
        # Volume envelope: attack, hold, then a decay (linear in dB) to sustain.
        t = np.arange(len(out), dtype=np.float32) / rate
        attack = _seconds(region.get(ATTACK), 0.001)
        hold = _seconds(region.get(HOLD), 0.001)
        decay = _seconds(region.get(DECAY), 0.001)
        sustain_db = min(100.0, max(0.0, region.get(SUSTAIN, 0) / 10.0))
        env_db = np.where(t < attack + hold, 0.0,
                          -np.minimum(1.0, (t - attack - hold) / max(decay, 1e-3)) * sustain_db)
        env = 10 ** (env_db / 20) * np.minimum(1.0, t / max(attack, 1e-3))
        out = out * env.astype(np.float32) * 10 ** (-region.get(ATTENUATION, 0) / 200)
        out = out.astype(np.float32)
        out *= _attack(len(out), rate, 0.001)
        # Match the engine's level conventions (as the synthesized piano does).
        out /= np.sqrt(np.mean(out[: int(0.25 * rate)] ** 2)) + 1e-9
        # Dynamics come from the engine's velocity curve, not from here: an
        # extra soft-layer cut made quiet touches nearly inaudible.
        out *= 0.2
        return _fade_tail(out, rate, 0.4)
