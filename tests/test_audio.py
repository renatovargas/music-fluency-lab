import numpy as np

from mfl.audio import Synth


def test_live_note_pitch_and_release():
    synth = Synth(48000)
    output = np.empty(4800, dtype=np.float32)
    synth.note_event("on", 69, 90)
    synth.render(output)
    frequencies = np.fft.rfftfreq(len(output), 1 / synth.rate)
    assert frequencies[np.abs(np.fft.rfft(output)).argmax()] == 440
    synth.note_event("off", 69, 0)
    for _ in range(3):
        synth.render(output)
    assert not output.any()


def test_demonstration_finishes_and_yields_to_playing():
    synth = Synth(48000)
    output = np.empty(4800, dtype=np.float32)
    synth.demonstrate({60, 64, 67})
    synth.render(output)
    assert output.any() and set(synth.demo) == {60, 64, 67}
    for _ in range(9):
        synth.render(output)
    assert not output.any()

    synth.demonstrate({60, 64, 67})
    synth.render(output)
    synth.note_event("on", 72, 80)
    for _ in range(3):
        synth.render(output)
    assert not synth.demo
    assert output.any() and set(synth.live) == {72}
