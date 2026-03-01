"""
Offline text-to-speech engine for HomePilot.

Uses Piper TTS for neural speech synthesis running
entirely on-device. Low latency, natural sounding.
"""

from __future__ import annotations

import io
import queue
import subprocess
import threading
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import TTSConfig

logger = get_logger("homepilot.tts")


class TTSEngine:
    """
    Piper-based offline text-to-speech engine.

    Features:
    - Neural TTS with natural sounding voices
    - Fully offline — no network required
    - Queued output to prevent overlapping speech
    - Configurable voice model and speech rate

    Usage:
        tts = TTSEngine(config)
        tts.initialize()
        tts.speak("Hello, I'm Jarvis!")
        tts.shutdown()
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._initialized = False
        self._output_device: int | None = None

    def initialize(self, output_device: int | None = None) -> None:
        """
        Initialize the TTS engine and start the speech worker.

        Args:
            output_device: Audio output device index. None = default.
        """
        self._output_device = output_device

        model_path = Path(self._config.model_path)
        if not model_path.exists():
            logger.warning(
                "Piper TTS model not found at: %s. "
                "TTS will attempt to use piper command directly.",
                model_path,
            )

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._speech_worker,
            daemon=True,
            name="tts-worker",
        )
        self._worker_thread.start()
        self._initialized = True
        logger.info("TTS engine initialized (model=%s).", self._config.model_path)

    def speak(self, text: str, priority: bool = False) -> None:
        """
        Queue text for speech synthesis.

        Args:
            text: Text to speak.
            priority: If True, clear queue and speak immediately.
        """
        if not self._initialized:
            logger.warning("TTS not initialized. Call initialize() first.")
            return

        if not text or not text.strip():
            return

        if priority:
            # Clear the queue for urgent messages
            while not self._speech_queue.empty():
                try:
                    self._speech_queue.get_nowait()
                except queue.Empty:
                    break

        self._speech_queue.put(text.strip())
        logger.debug("Queued for TTS: '%s'", text[:80])

    def speak_blocking(self, text: str) -> None:
        """
        Synthesize and play speech synchronously (blocks until done).

        Args:
            text: Text to speak.
        """
        if not text or not text.strip():
            return
        self._synthesize_and_play(text.strip())

    def shutdown(self) -> None:
        """Stop the TTS worker and release resources."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
        self._initialized = False
        logger.info("TTS engine shut down.")

    def _speech_worker(self) -> None:
        """Background worker that processes the speech queue."""
        while not self._stop_event.is_set():
            try:
                text = self._speech_queue.get(timeout=0.5)
                self._synthesize_and_play(text)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("TTS worker error: %s", e)

    def _synthesize_and_play(self, text: str) -> None:
        """
        Synthesize speech from text and play it.

        Tries Piper TTS first. Falls back to espeak if Piper
        is not available.
        """
        try:
            audio_data = self._piper_synthesize(text)
            if audio_data:
                self._play_audio(audio_data)
                return
        except Exception as e:
            logger.debug("Piper synthesis failed: %s. Trying fallback.", e)

        # Fallback to espeak (available on most Linux systems)
        try:
            self._espeak_fallback(text)
        except Exception as e:
            logger.error("All TTS methods failed: %s", e)

    def _piper_synthesize(self, text: str) -> bytes | None:
        """
        Synthesize speech using Piper TTS.

        Args:
            text: Text to synthesize.

        Returns:
            WAV audio bytes, or None on failure.
        """
        model_path = Path(self._config.model_path)

        # Try using piper as a Python module
        try:
            from piper import PiperVoice

            voice = PiperVoice.load(str(model_path))
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                voice.synthesize(text, wf)
            return buf.getvalue()
        except ImportError:
            pass

        # Try using piper CLI
        try:
            cmd = [
                "piper",
                "--model", str(model_path),
                "--output-raw",
            ]
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                # Convert raw PCM to WAV
                from homepilot.utils.audio_utils import pcm_to_wav_bytes
                return pcm_to_wav_bytes(result.stdout, sample_rate=22050)
        except FileNotFoundError:
            logger.debug("Piper CLI not found in PATH.")
        except Exception as e:
            logger.debug("Piper CLI error: %s", e)

        return None

    def _espeak_fallback(self, text: str) -> None:
        """Fallback TTS using espeak."""
        try:
            subprocess.run(
                ["espeak", "-s", "150", text],
                capture_output=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.error("espeak not found. Install with: sudo apt install espeak")

    def _play_audio(self, wav_data: bytes) -> None:
        """Play WAV audio data through the speaker."""
        import sounddevice as sd

        try:
            buf = io.BytesIO(wav_data)
            with wave.open(buf, "rb") as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())

            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            samples /= 32768.0

            # Apply volume
            samples *= self._config.volume

            if n_channels > 1:
                samples = samples.reshape(-1, n_channels)

            sd.play(samples, samplerate=sample_rate, device=self._output_device)
            sd.wait()

        except Exception as e:
            logger.error("Audio playback error: %s", e)
