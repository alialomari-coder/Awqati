"""Deterministic pure-sine confirmations, with unchanged rhythms and durations."""
from pathlib import Path
import math
import struct
import wave

RATE = 22050
PEAK = 21000  # -3.87 dBFS peak; 10.2 dB above dev10, without clipping.
PITCH = 1.5  # Raise the register a perfect fifth; preserve melodic intervals.
# Frequency in Hz, duration in ms. None is an exact silence interval.
PATTERNS = {
    "start": ((440, 500), (None, 100), (550, 500), (None, 100), (660, 1000)),
    "pause": ((550, 100), (440, 140)),
    "resume": ((440, 100), (660, 140)),
    "lap": ((550, 90), (None, 70), (550, 90)),
    "reset": ((330, 180),),
}


def pcm(pattern, *, amplitude=PEAK, pitch=PITCH):
    output = bytearray()
    for frequency, duration in pattern:
        count = RATE * duration // 1000
        fade = RATE // 100  # Ten ms attack/release avoids clicks.
        for index in range(count):
            envelope = min(1, index / fade, (count - 1 - index) / fade)
            value = int(amplitude * envelope * math.sin(2 * math.pi * frequency * pitch * index / RATE)) if frequency else 0
            output.extend(struct.pack("<h", value))
    return bytes(output)


def main():
    folder = Path(__file__).resolve().parents[1] / "addon/globalPlugins/awqati/sounds/stopwatch"
    folder.mkdir(parents=True, exist_ok=True)
    for name, pattern in PATTERNS.items():
        with wave.open(str(folder / (name + ".wav")), "wb") as stream:
            stream.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            stream.writeframes(pcm(pattern))


if __name__ == "__main__":
    main()
