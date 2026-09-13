import wave

import numpy as np

from visage.wav_io import write_wav


def test_write_wav_round_trips(tmp_path):
    sample_rate = 24000
    channels = 1
    samples = (np.sin(np.linspace(0, 10, sample_rate)) * 8000).astype(np.int16)
    pcm_bytes = samples.tobytes()

    path = tmp_path / "out.wav"
    write_wav(path, pcm_bytes, sample_rate=sample_rate, channels=channels)

    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == channels
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == sample_rate
        assert wf.readframes(wf.getnframes()) == pcm_bytes
