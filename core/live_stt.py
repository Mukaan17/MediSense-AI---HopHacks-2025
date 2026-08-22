# -*- coding: utf-8 -*-
"""Live chunked speech-to-text over raw PCM.

The frontend captures microphone audio with an AudioWorklet, downsamples to
16 kHz mono Int16 PCM, and streams raw frames over WS /ws/transcribe. This
module buffers those frames, detects utterance boundaries with an
energy-based VAD, and transcribes each utterance with faster-whisper.

Chunk transcription runs on its own single-worker executor so it never
queues behind full pipeline recomputes (which use the default executor via
asyncio.to_thread).
"""

import os
import struct
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # Int16 mono

# Energy-based VAD knobs (overridable via env for noisy environments).
SILENCE_RMS = int(os.getenv("STT_SILENCE_RMS", "500"))
SILENCE_FLUSH_MS = int(os.getenv("STT_SILENCE_FLUSH_MS", "700"))
MIN_SPEECH_MS = int(os.getenv("STT_MIN_SPEECH_MS", "300"))
MAX_BUFFER_MS = int(os.getenv("STT_MAX_BUFFER_MS", "15000"))

STT_MODEL = os.getenv("STT_LIVE_MODEL", "tiny.en")

# Single worker: chunks from all connections are serialized through one
# model instance, which is how ctranslate2 stays memory-sane on CPU.
stt_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-stt")

_fw_model = None
_fw_error: Optional[str] = None


def fw_available() -> bool:
    _get_model()
    return _fw_model is not None


def _get_model():
    global _fw_model, _fw_error
    if _fw_model is None and _fw_error is None:
        try:
            from faster_whisper import WhisperModel
            _fw_model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
            print(f"[STT] faster-whisper {STT_MODEL} loaded (live chunks)")
        except Exception as e:  # pragma: no cover - optional dependency
            _fw_error = str(e)
            print(f"[STT] faster-whisper unavailable: {e}")
    return _fw_model


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw mono Int16 PCM in a 44-byte WAV header."""
    byte_rate = sample_rate * BYTES_PER_SAMPLE
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16,
        1, 1, sample_rate, byte_rate, BYTES_PER_SAMPLE, 16,
        b"data", len(pcm),
    )
    return header + pcm


def transcribe_pcm(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> str:
    """Transcribe a raw 16 kHz mono Int16 PCM buffer. Returns '' when the
    model is unavailable or nothing was recognized."""
    model = _get_model()
    if model is None or not pcm:
        return ""
    wav = pcm_to_wav(pcm, sample_rate)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(wav)
        tmp.close()
        segments, _info = model.transcribe(
            tmp.name, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        print(f"[STT] chunk transcription failed: {e}")
        return ""
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


class UtteranceBuffer:
    """Accumulates PCM frames and decides when an utterance is complete.

    add() returns a PCM buffer to transcribe when trailing silence (or the
    max-buffer cap) closes an utterance, else None. flush() force-closes."""

    def __init__(self):
        self._buf = bytearray()
        self._trailing_silence_ms = 0.0
        self._speech_ms = 0.0

    @staticmethod
    def _frame_ms(frame: bytes) -> float:
        return len(frame) / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000.0

    @staticmethod
    def _rms(frame: bytes) -> float:
        usable = len(frame) - (len(frame) % BYTES_PER_SAMPLE)
        if usable < BYTES_PER_SAMPLE:
            return 0.0
        samples = memoryview(frame)[:usable].cast("h")
        total = 0
        for s in samples:
            total += s * s
        return (total / len(samples)) ** 0.5

    def add(self, frame: bytes) -> Optional[bytes]:
        if not frame:
            return None
        self._buf.extend(frame)
        ms = self._frame_ms(frame)
        rms = self._rms(frame)
        if rms < SILENCE_RMS:
            self._trailing_silence_ms += ms
        else:
            self._trailing_silence_ms = 0.0
            self._speech_ms += ms

        buffered_ms = len(self._buf) / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000.0
        ended = (self._speech_ms >= MIN_SPEECH_MS
                 and self._trailing_silence_ms >= SILENCE_FLUSH_MS)
        if ended or buffered_ms >= MAX_BUFFER_MS:
            return self.flush()
        return None

    def flush(self) -> Optional[bytes]:
        if self._speech_ms < MIN_SPEECH_MS:
            self._reset()
            return None
        out = bytes(self._buf)
        self._reset()
        return out

    def _reset(self) -> None:
        self._buf = bytearray()
        self._trailing_silence_ms = 0.0
        self._speech_ms = 0.0
