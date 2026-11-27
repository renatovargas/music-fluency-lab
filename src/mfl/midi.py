"""MIDI input with arrival timestamps. No fixed ALSA client numbers or
platform-specific paths.

Events are ``(kind, note, value, time)``:
  ("on", note, velocity, t)   key pressed (velocity > 0)
  ("off", note, velocity, t)  key released (note-off or zero-velocity note-on)
  ("pedal", 64, value, t)     sustain pedal (CC 64)
  ("pad", note, velocity, t)  drum pads on MIDI channel 10 (e.g. Launchkey pads)
Times are ``time.perf_counter()`` seconds, recorded when each message arrives,
so rhythm scoring is not limited by how often the screen polls.
"""

from __future__ import annotations

from queue import Empty, SimpleQueue
import time

IGNORED = ("DAW", "MIDI THROUGH", "THROUGH PORT", "RTMIDI")
PREFERRED = ("launchkey", "roland", "fp-30", "keystation", "digital piano", "casio", "yamaha", "kawai")


def decode(msg, t: float = 0.0):
    """Translate one raw MIDI message into an event tuple, or None."""
    if len(msg) < 3:
        return None
    status, channel = msg[0] & 0xF0, msg[0] & 0x0F
    if status in (0x80, 0x90):
        kind = "on" if status == 0x90 and msg[2] > 0 else "off"
        if channel == 9:
            return ("pad", msg[1], msg[2], t) if kind == "on" else None
        return (kind, msg[1], msg[2], t)
    if status == 0xB0 and msg[1] == 64:
        return ("pedal", 64, msg[2], t)
    return None


def choose_port(ports: list[str], preferred: str | None = None) -> int | None:
    candidates = [(i, n) for i, n in enumerate(ports) if not any(s in n.upper() for s in IGNORED)]
    if preferred:
        candidates = [(i, n) for i, n in candidates if preferred.lower() in n.lower()]
    if not candidates:
        return None
    best = next(((i, n) for i, n in candidates if any(s in n.lower() for s in PREFERRED)), candidates[0])
    return best[0]


class MidiInput:
    def __init__(self, preferred: str | None = None):
        import rtmidi

        self.input = rtmidi.MidiIn()
        self.input.ignore_types(sysex=True, timing=True, active_sense=True)
        ports = self.input.get_ports()
        index = choose_port(ports, preferred)
        if index is None:
            raise RuntimeError("No suitable MIDI input found. Connect a keyboard or run 'mfl devices'.")
        self.queue: SimpleQueue = SimpleQueue()
        self.input.open_port(index)
        self.name = ports[index].split(":")[0] if ":" in ports[index] else ports[index]
        self.input.set_callback(self._callback)

    def _callback(self, event, data=None):
        msg, _delta = event
        decoded = decode(msg, time.perf_counter())
        if decoded is not None:
            self.queue.put(decoded)

    def poll(self) -> list[tuple]:
        events = []
        while True:
            try:
                events.append(self.queue.get_nowait())
            except Empty:
                return events

    def close(self):
        try:
            self.input.cancel_callback()
        finally:
            self.input.close_port()


def list_ports() -> list[str]:
    import rtmidi

    return rtmidi.MidiIn().get_ports()
