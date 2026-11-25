"""MIDI input; no fixed ALSA client numbers or macOS-specific paths."""
import rtmidi

class MidiInput:
    def __init__(self, preferred: str | None = None):
        self.input = rtmidi.MidiIn()
        self.input.ignore_types(sysex=True, timing=True, active_sense=True)
        ports = self.input.get_ports()
        candidates = [(i, name) for i, name in enumerate(ports) if "DAW" not in name.upper() and "MIDI THROUGH" not in name.upper()]
        if preferred:
            candidates = [(i, n) for i, n in candidates if preferred.lower() in n.lower()]
        if not candidates:
            self.input.close_port()
            raise RuntimeError("No suitable MIDI input found. Connect a keyboard and run 'mfl devices'.")
        # Favor Novation or Roland when several inputs exist.
        i, name = next(((i, n) for i, n in candidates if any(s in n.lower() for s in ("launchkey", "roland", "fp-30"))), candidates[0])
        self.input.open_port(i)
        self.name = name

    def poll(self) -> list[tuple[str, int, int]]:
        events = []
        while True:
            event = self.input.get_message()
            if event is None:
                break
            msg, _delta = event
            if len(msg) < 3:
                continue
            status = msg[0] & 0xF0
            if status == 0x90 and msg[2] > 0:
                events.append(("on", msg[1], msg[2]))
            elif status == 0x80 or (status == 0x90 and msg[2] == 0):
                events.append(("off", msg[1], msg[2]))
        return events

    def close(self):
        self.input.close_port()
