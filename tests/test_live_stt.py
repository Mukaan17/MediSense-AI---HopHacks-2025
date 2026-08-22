import math
import struct

from core.live_stt import UtteranceBuffer, pcm_to_wav


def _frame(amp: int, ms: int = 250) -> bytes:
    n = int(16000 * ms / 1000)
    return b"".join(struct.pack("<h", int(amp * math.sin(i / 5.0))) for i in range(n))


def test_wav_header_is_byte_exact():
    pcm = b"\x00\x01" * 16000
    wav = pcm_to_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert struct.unpack("<I", wav[24:28])[0] == 16000  # sample rate
    assert struct.unpack("<H", wav[22:24])[0] == 1      # mono
    assert len(wav) == 44 + len(pcm)


def test_vad_flushes_once_after_speech_then_silence():
    buf = UtteranceBuffer()
    emissions = []
    for _ in range(4):  # 1s of speech-level energy
        assert buf.add(_frame(8000)) is None
    for _ in range(4):  # 1s of silence: flush after the 700ms threshold
        out = buf.add(_frame(30))
        if out:
            emissions.append(out)
    assert len(emissions) == 1
    assert len(emissions[0]) > 16000  # >0.5s of audio retained


def test_silence_only_never_emits():
    buf = UtteranceBuffer()
    for _ in range(8):
        assert buf.add(_frame(20)) is None
    assert buf.flush() is None
