"""Keep the old byte-level sound contract while testing authorized dev11 gain/pitch."""
import io
import wave
from tools.build_stopwatch_sounds import PATTERNS, pcm


def assert_updated_stopwatch_sound(test, original, current):
    with wave.open(io.BytesIO(original), "rb") as old:
        params, data = old.getparams(), old.readframes(old.getnframes())
    pattern = PATTERNS[current.stem]
    # The exact previous waveform remains reproducible; no rhythm was lost.
    test.assertEqual(data, pcm(pattern, amplitude=6500, pitch=1))
    legacy = io.BytesIO()
    with wave.open(legacy, "wb") as stream:
        stream.setparams(params)
        stream.writeframes(data)
    test.assertEqual(original, legacy.getvalue())
    with wave.open(str(current), "rb") as new:
        test.assertEqual(params, new.getparams())
        new_data = new.readframes(new.getnframes())
    test.assertEqual(pcm(pattern), new_data)
    test.assertNotEqual(data, new_data)
