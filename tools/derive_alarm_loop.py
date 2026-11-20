"""Reproduce the owner's approved loop without processing its retained samples."""
from pathlib import Path
import hashlib
import wave

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = "0b395a8f5b9aa2d30f6dd7629af13ae865515b1acc5f3b945030151736a379a8"
DERIVED_HASH = "6aad549639847a80ed4dce0b14309c1c3ca2fb0e19d30ae696730cbafe5f1753"


def main():
    source = ROOT / "data_sources/personal_alarm/alarm.original.wav"
    target = ROOT / "addon/globalPlugins/awqati/sounds/alarms/alarm.wav"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError("The source differs from the approved original; no output written")
    with wave.open(str(source), "rb") as stream:
        params = stream.getparams()
        if (params.nchannels, params.sampwidth, params.framerate, params.nframes) != (2, 2, 44100, 529200):
            raise ValueError("Unexpected source PCM format")
        stream.setpos(44100)
        data = stream.readframes(params.nframes - 44100)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as stream:
        stream.setparams(params)
        stream.writeframes(data)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == DERIVED_HASH
    print("Approved eleven-second alarm loop reproduced; original unchanged.")


if __name__ == "__main__":
    main()
