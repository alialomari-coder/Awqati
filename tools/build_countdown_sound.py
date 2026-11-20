"""Reproducible draft countdown tone, pending the owner's listening approval."""
from pathlib import Path
import wave
import math
import random
import struct
from build_stopwatch_sounds import RATE, pcm

PATTERN = ((880, 160), (None, 90), (660, 160), (None, 90), (880, 300))
CONFIRMATIONS = {
    "start": ((440, 100), (660, 140)),
    "pause": ((550, 100), (440, 140)),
    "resume": ((440, 100), (660, 140)),
    "restart": ((660, 90), (None, 70), (660, 90)),
    "cancel": ((550, 80), (None, 40), (330, 160)),
}


def tick_pcm(tock=False):
    """A soft, damped mechanical impulse, not a square-wave or digital click."""
    rng = random.Random(230 if tock else 170)
    count = RATE * 35 // 1000
    output, filtered = bytearray(), 0.0
    frequency = 1850 if tock else 1550
    for index in range(count):
        t = index / RATE
        filtered = .45 * rng.uniform(-1, 1) + .55 * filtered
        envelope = min(1, index / 12, (count - 1 - index) / 24) * math.exp(-t / .006)
        ringing = .55 * math.sin(2 * math.pi * frequency * t) + .25 * math.sin(2 * math.pi * frequency * 2.31 * t)
        value = int(6000 * envelope * (ringing + .2 * filtered))
        output.extend(struct.pack("<h", value))
    return bytes(output)


def main():
    folder = Path(__file__).resolve().parents[1] / "addon/globalPlugins/awqati/sounds/timers"
    folder.mkdir(parents=True, exist_ok=True)
    sounds = {"finished": pcm(PATTERN), **{name: pcm(pattern) for name, pattern in CONFIRMATIONS.items()},
        "tick": tick_pcm(), "tock": tick_pcm(True)}
    for name, data in sounds.items():
        with wave.open(str(folder / (name + ".wav")), "wb") as stream:
            stream.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            stream.writeframes(data)


if __name__ == "__main__":
    main()
