"""
Speech-to-text engine for HomePilot.

Hybrid approach:
  1. Google Speech Recognition — free, excellent accuracy, needs internet
  2. Faster-Whisper (offline) — OpenAI Whisper, great with accents
  3. Vosk (fallback) — lightweight, lower accuracy

Automatically falls back to offline engines when there's no internet.
"""

from __future__ import annotations

import io
import json
import struct
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import AudioConfig, STTConfig

logger = get_logger("homepilot.stt")


class STTEngine:
    """
    Hybrid STT — Google online, Whisper/Vosk offline.

    Tries Google Speech Recognition first for best accuracy,
    falls back to Faster-Whisper or Vosk when offline.

    Usage:
        engine = STTEngine(stt_config, audio_config)
        engine.initialize()
        transcript = engine.transcribe(audio_source)
    """

    def __init__(self, stt_config: STTConfig, audio_config: AudioConfig) -> None:
        self._stt_config = stt_config
        self._audio_config = audio_config
        self._engine_type: str = ""
        self._model: object | None = None
        self._recognizer: object | None = None
        self._google_available: bool | None = None  # Cached connectivity
        self._google_check_time: float = 0

    def initialize(self) -> None:
        """
        Initialize the STT engine.

        Tries Faster-Whisper first, falls back to Vosk.
        """
        engine = self._stt_config.engine.lower()

        if engine == "whisper":
            if self._init_whisper():
                return
            logger.warning("Whisper init failed, falling back to Vosk.")

        if engine == "vosk" or self._engine_type == "":
            self._init_vosk()

    def _init_whisper(self) -> bool:
        """Initialize Faster-Whisper engine."""
        try:
            from faster_whisper import WhisperModel

            # Determine model size from config or default to "base"
            model_name = self._stt_config.model_path
            # If it's a Vosk path, use whisper default
            if "vosk" in model_name.lower():
                model_name = "base"

            # Determine compute type based on platform
            import platform
            if platform.machine().startswith("arm") or platform.machine() == "aarch64":
                compute_type = "int8"  # RPi needs int8
            else:
                compute_type = "int8"  # Safe default, works everywhere

            logger.info(
                "Loading Whisper model '%s' (compute=%s)...",
                model_name, compute_type,
            )

            self._model = WhisperModel(
                model_name,
                device="cpu",
                compute_type=compute_type,
            )
            self._engine_type = "whisper"
            logger.info("✅ Whisper STT ready (model=%s)", model_name)
            return True

        except ImportError:
            logger.info("faster-whisper not installed.")
            return False
        except Exception as e:
            logger.warning("Whisper init error: %s", e)
            return False

    def _init_vosk(self) -> None:
        """Initialize Vosk engine (fallback)."""
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        model_path = Path(self._stt_config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found at: {model_path}\n"
                f"Download from https://alphacephei.com/vosk/models\n"
                f"Recommended: vosk-model-small-en-us-0.15 (~40MB)"
            )

        self._model = Model(str(model_path))
        self._engine_type = "vosk"
        logger.info("Vosk STT model loaded from: %s", model_path)

    def transcribe(
        self,
        audio_source,
        silence_timeout: float | None = None,
        max_duration: float | None = None,
    ) -> str:
        """
        Transcribe speech from an audio source.

        Priority: Google STT (online) → Whisper (offline) → Vosk (offline)

        Args:
            audio_source: Object with a `read_frame(timeout)` method
                          that returns numpy int16 arrays.
            silence_timeout: Seconds of silence before stopping.
            max_duration: Maximum recording duration in seconds.

        Returns:
            Transcribed text string, or empty string if nothing recognized.
        """
        # First, record the audio (shared across all engines)
        silence_timeout = silence_timeout or self._audio_config.vad_silence_timeout
        max_duration = max_duration or self._audio_config.max_record_seconds

        audio_buffer = self._record_audio(audio_source, silence_timeout, max_duration)
        if not audio_buffer:
            return ""

        audio_data = np.concatenate(audio_buffer)

        # 1. Try Google STT first (best accuracy, needs internet)
        if self._is_google_available():
            try:
                result = self._transcribe_google(audio_data)
                if result:
                    logger.info("STT [Google] result: '%s'", result)
                    return result
            except Exception as e:
                logger.debug("Google STT failed: %s. Falling back.", e)
                self._google_available = False

        # 2. Try Whisper (offline, good accuracy)
        if self._engine_type == "whisper":
            logger.info("🎙️ STT [Whisper] processing...")
            result = self._transcribe_whisper_from_buffer(audio_data)
            if result:
                return result

        # 3. Try Vosk (offline, lightweight)
        if self._engine_type == "vosk":
            logger.info("🎙️ STT [Vosk] processing...")
            return self._transcribe_vosk_from_buffer(audio_data)

        return ""

    def _is_google_available(self) -> bool:
        """Check if Google STT is reachable (cached for 60 seconds)."""
        now = time.monotonic()
        if self._google_available is not None and (now - self._google_check_time) < 60:
            return self._google_available

        try:
            import urllib.request
            urllib.request.urlopen("https://www.google.com", timeout=2)
            self._google_available = True
        except Exception:
            self._google_available = False

        self._google_check_time = now
        return self._google_available

    def _record_audio(
        self,
        audio_source,
        silence_timeout: float,
        max_duration: float,
    ) -> list[np.ndarray]:
        """Record audio frames from source until silence or max duration."""
        audio_buffer = []
        start_time = time.monotonic()
        last_audio_time = start_time
        has_audio = False

        logger.debug("Recording (timeout=%.1fs, max=%.1fs)", silence_timeout, max_duration)

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > max_duration:
                break

            frame = audio_source.read_frame(timeout=0.5)
            if frame is None:
                continue

            frame = self._normalize_audio(frame)
            audio_buffer.append(frame)

            energy = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
            if energy > 200:
                has_audio = True
                last_audio_time = time.monotonic()

            if has_audio:
                silence_gap = time.monotonic() - last_audio_time
                if silence_gap > silence_timeout:
                    logger.debug("Silence detected after %.1fs.", silence_gap)
                    break

        return audio_buffer

    def _transcribe_google(self, audio_data: np.ndarray) -> str:
        """
        Transcribe using Google Speech Recognition (free, no API key).

        Uses the `speech_recognition` library.
        """
        try:
            import speech_recognition as sr
        except ImportError:
            logger.debug("speech_recognition not installed. pip install SpeechRecognition")
            return ""

        # Convert numpy int16 array to WAV bytes for SpeechRecognition
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._audio_config.sample_rate)
            wf.writeframes(audio_data.astype(np.int16).tobytes())

        wav_buf.seek(0)
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_buf) as source:
            audio = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio)
            return text.strip()
        except sr.UnknownValueError:
            logger.debug("Google STT: could not understand audio")
            return ""
        except sr.RequestError as e:
            logger.debug("Google STT request failed: %s", e)
            self._google_available = False
            return ""

    # ─────────────────────────────────────────────────────
    # Whisper transcription
    # ─────────────────────────────────────────────────────

    def _transcribe_whisper_from_buffer(self, audio_data: np.ndarray) -> str:
        """Transcribe pre-recorded audio using Faster-Whisper."""
        audio_float = audio_data.astype(np.float32) / 32768.0

        try:
            segments, info = self._model.transcribe(
                audio_float,
                beam_size=3,
                language="en",
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )

            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())
                logger.debug(
                    "Whisper segment [%.1fs-%.1fs]: '%s'",
                    segment.start, segment.end, segment.text.strip(),
                )

            text = " ".join(text_parts).strip()
            logger.info("STT [Whisper] result: '%s'", text or "(empty)")
            return text

        except Exception as e:
            logger.error("Whisper transcription error: %s", e)
            return ""

    def _transcribe_vosk_from_buffer(self, audio_data: np.ndarray) -> str:
        """Transcribe pre-recorded audio using Vosk."""
        try:
            from vosk import KaldiRecognizer
        except ImportError:
            logger.debug("Vosk not available.")
            return ""

        if self._model is None and self._engine_type != "vosk":
            return ""

        recognizer = KaldiRecognizer(self._model, self._audio_config.sample_rate)
        recognizer.SetWords(True)

        audio_bytes = audio_data.astype(np.int16).tobytes()

        # Feed in chunks
        chunk_size = self._audio_config.frame_length * 2  # bytes
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            recognizer.AcceptWaveform(chunk)

        final_result = json.loads(recognizer.FinalResult())
        text = final_result.get("text", "").strip()
        logger.info("STT [Vosk] result: '%s'", text or "(empty)")
        return text

    # ─────────────────────────────────────────────────────
    # Audio preprocessing
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _normalize_audio(
        frame: np.ndarray,
        target_peak: float = 0.8,
    ) -> np.ndarray:
        """
        Normalize audio frame to improve STT accuracy.

        Amplifies quiet audio so the STT model gets a stronger
        signal. Critical for laptop/USB mics.
        """
        if len(frame) == 0:
            return frame

        peak = np.max(np.abs(frame))
        if peak == 0:
            return frame

        target_level = target_peak * 32767
        gain = target_level / peak
        gain = min(gain, 10.0)

        if gain > 1.1:
            amplified = (frame.astype(np.float32) * gain)
            amplified = np.clip(amplified, -32768, 32767)
            return amplified.astype(np.int16)

        return frame

    def cleanup(self) -> None:
        """Release STT resources."""
        self._model = None
        self._recognizer = None
        logger.info("STT engine released.")
