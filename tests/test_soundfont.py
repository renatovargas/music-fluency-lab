import struct

import numpy as np

from mfl.audio.soundfont import SoundFont, SoundFontPiano


def chunk(cid: bytes, payload: bytes) -> bytes:
    return cid + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")


def tiny_sf2(path, rate=44100):
    """One preset → one instrument → one 440 Hz sample (root A4, unlooped)."""
    tone = (np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 20000).astype("<i2")
    smpl = tone.tobytes() + b"\0" * 92  # spec: 46 zero samples after each sample
    name = lambda text: text.encode().ljust(20, b"\0")  # noqa: E731
    phdr = struct.pack("<20sHHHIII", name("Piano"), 0, 0, 0, 0, 0, 0) + \
        struct.pack("<20sHHHIII", name("EOP"), 0, 0, 1, 0, 0, 0)
    pbag = struct.pack("<HH", 0, 0) + struct.pack("<HH", 1, 0)
    pgen = struct.pack("<Hh", 41, 0) + struct.pack("<Hh", 0, 0)
    inst = struct.pack("<20sH", name("Inst"), 0) + struct.pack("<20sH", name("EOI"), 1)
    ibag = struct.pack("<HH", 0, 0) + struct.pack("<HH", 2, 0)
    igen = struct.pack("<HBB", 43, 0, 127) + struct.pack("<Hh", 53, 0) + struct.pack("<Hh", 0, 0)
    shdr = struct.pack("<20sIIIIIBbHH", name("A4"), 0, len(tone), 0, 0, rate, 69, 0, 0, 1) + \
        struct.pack("<20sIIIIIBbHH", name("EOS"), 0, 0, 0, 0, 0, 0, 0, 0, 0)
    pdta = b"pdta" + b"".join(chunk(c, d) for c, d in (
        (b"phdr", phdr), (b"pbag", pbag), (b"pmod", b"\0" * 10), (b"pgen", pgen), (b"inst", inst),
        (b"ibag", ibag), (b"imod", b"\0" * 10), (b"igen", igen), (b"shdr", shdr)))
    body = b"sfbk" + chunk(b"LIST", b"INFO" + chunk(b"ifil", struct.pack("<HH", 2, 1))) + \
        chunk(b"LIST", b"sdta" + chunk(b"smpl", smpl)) + chunk(b"LIST", pdta)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def test_soundfont_regions_and_pitched_render(tmp_path):
    path = tiny_sf2(tmp_path / "tiny.sf2")
    font = SoundFont(path)
    assert font.presets[0][0] == "Piano" and len(font.regions()) == 1
    piano = SoundFontPiano(path)
    out = piano.render(72, 1, 48000)  # C5 from an A4 sample, at a different output rate
    segment = out[4800:4800 + 16384]
    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
    peak = np.fft.rfftfreq(len(segment), 1 / 48000)[spectrum.argmax()]
    assert abs(peak - 523.25) < 4
    assert np.isfinite(out).all() and np.abs(out).max() < 1.0
