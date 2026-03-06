"""
Offline speech-to-text engine for HomePilot.

Uses Vosk for fully local, real-time transcription.
Optimized for Raspberry Pi with small model support.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import AudioConfig, STTConfig

logger = get_logger("homepilot.stt")


class STTEngine:
    """
    Vosk-based offline speech-to-text engine.

    Streams audio frames to a Vosk recognizer and returns
    the final transcription when silence is detected or
    the recording timeout is reached.

    Usage:
        engine = STTEngine(stt_config, audio_config)
        engine.initialize()
        transcript = engine.transcribe(audio_source)
    """

    def __init__(self, stt_config: STTConfig, audio_config: AudioConfig) -> None:
        self._stt_config = stt_config
        self._audio_config = audio_config
        self._model: object | None = None
        self._recognizer: object | None = None

    def initialize(self) -> None:
        """
        Load the Vosk model from disk.

        The model path should point to an extracted Vosk model directory.
        Download models from: https://alphacephei.com/vosk/models
        """
        from vosk import Model, SetLogLevel

        # Suppress Vosk's verbose logging
        SetLogLevel(-1)

        model_path = Path(self._stt_config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found at: {model_path}\n"
                f"Download a model from https://alphacephei.com/vosk/models\n"
                f"Recommended: vosk-model-small-en-us-0.15 (~40MB)"
            )

        self._model = Model(str(model_path))
        logger.info("Vosk STT model loaded from: %s", model_path)

    def transcribe(
        self,
        audio_source,
        silence_timeout: float | None = None,
        max_duration: float | None = None,
    ) -> str:
        """
        Transcribe speech from an audio source.

        Reads frames from the audio source until silence is detected
        or the max duration is reached.

        Args:
            audio_source: Object with a `read_frame(timeout)` method
                          that returns numpy int16 arrays (e.g., AudioStream).
            silence_timeout: Seconds of silence before stopping.
                             Defaults to config value.
            max_duration: Maximum recording duration in seconds.
                          Defaults to config value.

        Returns:
            Transcribed text string, or empty string if nothing was recognized.
        """
        from vosk import KaldiRecognizer

        if self._model is None:
            raise RuntimeError("STT engine not initialized. Call initialize() first.")

        silence_timeout = silence_timeout or self._audio_config.vad_silence_timeout
        max_duration = max_duration or self._audio_config.max_record_seconds

        recognizer = KaldiRecognizer(self._model, self._audio_config.sample_rate)
        recognizer.SetWords(True)

        start_time = time.monotonic()
        last_speech_time = start_time
        has_speech = False
        partial_text = ""

        logger.debug("STT listening started (timeout=%.1fs, max=%.1fs)",
                      silence_timeout, max_duration)

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > max_duration:
                logger.debug("STT max duration reached (%.1fs).", max_duration)
                break

            frame = audio_source.read_frame(timeout=0.5)
            if frame is None:
                continue

            # ── Audio preprocessing ──
            # Normalize audio levels for better STT accuracy
            frame = self._normalize_audio(frame)

            # Convert to bytes for Vosk
            audio_bytes = frame.astype(np.int16).tobytes()

            if recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    logger.info("STT final result: '%s'", text)
                    return text
            else:
                partial = json.loads(recognizer.PartialResult())
                partial_text = partial.get("partial", "").strip()
                if partial_text:
                    has_speech = True
                    last_speech_time = time.monotonic()
                    logger.debug("STT partial: '%s'", partial_text)

            # Silence detection — if we had speech, check for silence gap
            if has_speech:
                silence_gap = time.monotonic() - last_speech_time
                if silence_gap > silence_timeout:
                    logger.debug("Silence detected after %.1fs.", silence_gap)
                    break

        # Get final result
        final_result = json.loads(recognizer.FinalResult())
        text = final_result.get("text", "").strip()
        logger.info("STT transcription: '%s'", text or "(empty)")
        return text

    @staticmethod
    def _normalize_audio(
        frame: np.ndarray,
        target_peak: float = 0.8,
    ) -> np.ndarray:
        """
        Normalize audio frame to improve STT accuracy.

        Amplifies quiet audio so the Vosk model gets a stronger
        signal. This is critical for laptop mics and low-gain
        USB mics.

        Args:
            frame: int16 PCM audio samples.
            target_peak: Target peak level (0.0–1.0 of int16 max).

        Returns:
            Normalized int16 audio frame.
        """
        if len(frame) == 0:
            return frame

        # Calculate current peak level
        peak = np.max(np.abs(frame))
        if peak == 0:
            return frame

        # Calculate gain needed
        target_level = target_peak * 32767
        gain = target_level / peak

        # Limit gain to avoid amplifying noise too much
        gain = min(gain, 10.0)

        if gain > 1.1:  # Only apply if meaningful
            amplified = (frame.astype(np.float32) * gain)
            # Clip to int16 range
            amplified = np.clip(amplified, -32768, 32767)
            return amplified.astype(np.int16)

        return frame

    def cleanup(self) -> None:
        """Release STT resources."""
        self._model = None
        self._recognizer = None
        logger.info("STT engine released.")
