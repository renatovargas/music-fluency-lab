import numpy as np
import pytest

from mfl.audio.engine import Engine, NoteEvent
from mfl.audio.instruments import build_instruments


@pytest.fixture(scope="module")
def engine():
    e = Engine(48000, disk_cache=False, warm=False)
    for key in ("drums", "bass"):
        e.banks[key].warm()
    for root in (57, 60, 63, 66, 69):
        for layer in (0, 1):
            e.banks["piano"].ensure(root, layer)
            e.banks["epiano"].ensure(root, layer)
    e.offset = 0.0
    return e


def render(e, seconds):
    return np.concatenate([e.render(256) for _ in range(int(seconds * e.rate / 256))])


def dominant_hz(signal, rate):
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return np.fft.rfftfreq(len(signal), 1 / rate)[spectrum.argmax()]


def fundamental_strength(signal, rate, hz):
    """Energy near ``hz`` relative to the strongest spectral peak."""
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    near = spectrum[(freqs > hz * 0.98) & (freqs < hz * 1.02)].max()
    return near / spectrum.max()


@pytest.mark.parametrize("key", ["piano", "epiano", "organ", "pad"])
def test_instruments_play_in_tune_and_release(engine, key):
    engine.set_instrument(key)
    engine.note_on(69, 100)
    out = render(engine, 0.6)
    assert out.shape[1] == 2 and np.isfinite(out).all()
    assert fundamental_strength(out[int(0.2 * 48000):, 0], 48000, 440) > 0.3
    assert np.abs(out).max() <= 1.0
    engine.note_off(69)
    render(engine, 3.0)
    assert not engine.voices
    tail = render(engine, 2.0)  # reverb dies away
    assert np.abs(tail).max() < 1e-3


def test_neighbouring_notes_are_resampled(engine):
    engine.set_instrument("piano")
    engine.note_on(70, 90)  # between rendered roots
    out = render(engine, 0.5)
    assert abs(dominant_hz(out[4800:, 0], 48000) - 466.16) < 5
    engine.note_off(70)
    render(engine, 2.5)


def test_level_is_healthy_and_limited(engine):
    engine.set_instrument("piano")
    for n in (60, 64, 67):
        engine.note_on(n, 100)
    triad = render(engine, 0.4)
    assert 0.25 < np.abs(triad).max() <= 1.0, "a firm triad should be clearly audible"
    for n in range(48, 80):
        engine.note_on(n, 127)
    loud = render(engine, 0.4)
    assert np.abs(loud).max() <= 1.0
    for n in range(48, 80):
        engine.note_off(n)
    render(engine, 3.0)


def test_scheduled_events_are_sample_accurate_and_cancellable(engine):
    start = engine.wall_for(engine.frame) + 0.1
    engine.play([NoteEvent(start, 76, 110, 0.05, "drums")], tag="backing")
    out = render(engine, 0.3)
    first = np.argmax(np.abs(out[:, 0]) > 0.01)
    assert abs(first - int(0.1 * 48000)) < 300
    engine.play([NoteEvent(engine.wall_for(engine.frame) + 0.2, 60, 90, 1.0)], tag="demo")
    engine.stop("demo")
    render(engine, 0.6)
    assert not [v for v in engine.voices if v.tag == "demo"]
    render(engine, 2.0)


def test_live_note_cuts_demo_and_pedal_sustains(engine):
    engine.set_instrument("piano")
    engine.play([NoteEvent(engine.wall_for(engine.frame), 60, 90, 2.0)], tag="demo", source="demo")
    render(engine, 0.1)
    assert any(v.source == "demo" for v in engine.voices)
    engine.note_on(64, 90)
    render(engine, 0.2)
    assert not any(v.source == "demo" for v in engine.voices)
    engine.pedal(True)
    engine.note_off(64)
    render(engine, 0.5)
    assert any(v.source == "live" and not v.releasing for v in engine.voices)
    engine.pedal(False)
    render(engine, 3.0)
    assert not engine.voices


def test_drum_kit_renders_every_sound():
    drums = build_instruments()["drums"]
    for note in drums.roots():
        sample = drums.render(note, 1, 48000)
        assert np.isfinite(sample).all() and 0.05 < np.abs(sample).max() <= 1.0
