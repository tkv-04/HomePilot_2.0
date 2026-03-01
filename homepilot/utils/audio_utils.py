"""
Audio utility functions for HomePilot.

Provides helpers for WAV playback, format conversion,
and ambient noise measurement.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import numpy.typing as npt

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.audio_utils")


def play_wav(file_path: str | Path, device: int | None = None) -> None:
    """
    Play a WAV file through the specified audio output device.

    Args:
        file_path: Path to the WAV file.
        device: Output device index. None = system default.
    """
    import sounddevice as sd

    path = Path(file_path)
    if not path.exists():
        logger.warning("Sound file not found: %s", path)
        return

    try:
        import soundfile as sf
        data, samplerate = sf.read(str(path), dtype="float32")
        sd.play(data, samplerate=samplerate, device=device)
        sd.wait()
    except Exception as e:
        logger.error("Failed to play WAV %s: %s", path, e)


def play_audio_data(
    audio_data: bytes,
    sample_rate: int = 22050,
    device: int | None = None,
) -> None:
    """
    Play raw audio bytes (16-bit PCM or WAV format).

    Args:
        audio_data: Raw audio bytes.
        sample_rate: Sample rate of the audio.
        device: Output device index.
    """
    import sounddevice as sd

    try:
        # Try parsing as WAV first
        with io.BytesIO(audio_data) as buf:
            try:
                with wave.open(buf, "rb") as wf:
                    sample_rate = wf.getframerate()
                    n_channels = wf.getnchannels()
                    frames = wf.readframes(wf.getnframes())
                    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                    samples /= 32768.0
                    if n_channels > 1:
                        samples = samples.reshape(-1, n_channels)
            except wave.Error:
                # Treat as raw 16-bit PCM
                samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                samples /= 32768.0

        sd.play(samples, samplerate=sample_rate, device=device)
        sd.wait()
    except Exception as e:
        logger.error("Failed to play audio data: %s", e)


def measure_ambient_noise(
    duration: float = 1.0,
    sample_rate: int = 16000,
    device: int | None = None,
) -> float:
    """
    Record ambient noise and return its RMS level.

    Args:
        duration: Recording duration in seconds.
        sample_rate: Sample rate.
        device: Input device index.

    Returns:
        RMS noise level as a float.
    """
    import sounddevice as sd

    try:
        frames = int(duration * sample_rate)
        recording = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
        )
        sd.wait()

        samples = recording.flatten().astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2)))
        logger.info("Ambient noise RMS: %.2f", rms)
        return rms
    except Exception as e:
        logger.error("Failed to measure ambient noise: %s", e)
        return 0.0


def pcm_to_wav_bytes(
    pcm_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """
    Convert raw PCM bytes to WAV format in memory.

    Args:
        pcm_data: Raw PCM audio bytes.
        sample_rate: Sample rate.
        channels: Number of audio channels.
        sample_width: Bytes per sample (2 = 16-bit).

    Returns:
        WAV file bytes.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()
