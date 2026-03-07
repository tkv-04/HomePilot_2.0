"""
Text-to-speech engine for HomePilot.

Hybrid approach:
  1. gTTS (Google Translate TTS) — free, natural sounding, needs internet
  2. Piper TTS — neural synthesis, fully offline
  3. espeak / Windows SAPI — last-resort fallback

Automatically falls back to offline engines when there's no internet.
"""

from __future__ import annotations

import io
import platform
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
    Hybrid TTS engine — Google online, Piper/espeak offline.

    Features:
    - gTTS (Google) when internet is available — natural & free
    - Piper TTS for offline — neural voices, good quality
    - Automatic fallback between online and offline
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
        self._google_available: bool | None = None  # Cached connectivity
        self._google_check_time: float = 0  # Last connectivity check

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
        Synthesize speech and play it.

        Priority: gTTS (Google) → Piper (offline) → espeak/SAPI
        Falls back automatically when internet is unavailable.
        """
        # 1. Try Google TTS (free, great quality, needs internet)
        try:
            if self._is_google_available():
                audio_data = self._gtts_synthesize(text)
                if audio_data:
                    logger.info("🔊 TTS [Google] speaking: '%s'", text[:60])
                    self._play_audio(audio_data)
                    return
        except Exception as e:
            logger.debug("gTTS failed: %s. Falling back to Piper.", e)
            self._google_available = False  # Cache the failure

        # 2. Try Piper TTS (offline, good quality)
        try:
            audio_data = self._piper_synthesize(text)
            if audio_data:
                self._play_audio(audio_data)
                return
        except Exception as e:
            logger.debug("Piper synthesis failed: %s. Trying fallback.", e)

        # 3. Fallback: espeak (Linux) or SAPI (Windows)
        try:
            self._platform_tts_fallback(text)
        except Exception as e:
            logger.error("All TTS methods failed: %s", e)

    def _is_google_available(self) -> bool:
        """Check if Google TTS is reachable (cached for 60 seconds)."""
        import time as _time
        now = _time.monotonic()

        # Re-check every 60 seconds
        if self._google_available is not None and (now - self._google_check_time) < 60:
            return self._google_available

        try:
            import urllib.request
            urllib.request.urlopen("https://translate.google.com", timeout=2)
            self._google_available = True
        except Exception:
            self._google_available = False

        self._google_check_time = now
        return self._google_available

    def _gtts_synthesize(self, text: str) -> bytes | None:
        """
        Synthesize speech using gTTS (Google Translate TTS).

        Free, no API key needed, sounds natural.
        Requires internet connection.

        Returns:
            WAV audio bytes, or None on failure.
        """
        import tempfile
        import os

        try:
            from gtts import gTTS

            tts = gTTS(text=text, lang="en", slow=False)

            # gTTS outputs MP3 — save to temp file, then read as WAV
            mp3_path = os.path.join(tempfile.gettempdir(), "homepilot_tts.mp3")
            tts.save(mp3_path)

            # Read MP3 and convert to WAV using numpy + wave
            # Use soundfile which can read MP3 from file path
            try:
                import soundfile as sf
                audio_data, sample_rate = sf.read(mp3_path, dtype="int16")
            except (ImportError, Exception):
                # Fallback: use subprocess with ffmpeg if available
                wav_path = os.path.join(tempfile.gettempdir(), "homepilot_tts.wav")
                try:
                    import subprocess
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "22050",
                         "-ac", "1", "-f", "wav", wav_path],
                        capture_output=True, timeout=10,
                    )
                    with open(wav_path, "rb") as f:
                        return f.read()
                except (FileNotFoundError, Exception) as e:
                    logger.debug("ffmpeg not available for MP3→WAV: %s", e)
                    # Last resort: use the MP3 bytes directly with pygame/playsound
                    try:
                        import playsound
                        playsound.playsound(mp3_path)
                        return None  # Already played
                    except (ImportError, Exception):
                        # Play MP3 directly on Windows
                        import platform
                        if platform.system() == "Windows":
                            try:
                                import subprocess
                                # Use Windows media player via PowerShell
                                ps = (
                                    f'$player = New-Object System.Media.SoundPlayer; '
                                    f'Add-Type -AssemblyName presentationCore; '
                                    f'$mp = New-Object System.Windows.Media.MediaPlayer; '
                                    f'$mp.Open("{mp3_path}"); '
                                    f'$mp.Play(); '
                                    f'Start-Sleep -Seconds 5; '
                                    f'$mp.Stop()'
                                )
                                subprocess.run(
                                    ["powershell", "-Command", ps],
                                    capture_output=True, timeout=15,
                                )
                                return None  # Already played
                            except Exception:
                                pass
                        return None

            # Convert to WAV bytes
            wav_buf = io.BytesIO()
            import wave as wave_mod
            with wave_mod.open(wav_buf, "wb") as wf:
                wf.setnchannels(1 if audio_data.ndim == 1 else audio_data.shape[1])
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())

            logger.debug("gTTS synthesis successful (%d bytes)", wav_buf.tell())
            return wav_buf.getvalue()

        except ImportError:
            logger.debug("gTTS not installed. pip install gTTS")
            return None
        except Exception as e:
            logger.debug("gTTS error: %s", e)
            self._google_available = False
            return None

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

    def _platform_tts_fallback(self, text: str) -> None:
        """
        Platform-aware TTS fallback.

        Linux: uses espeak
        Windows: uses Windows SAPI (built-in speech synthesizer)
        """
        if platform.system() == "Windows":
            try:
                # Windows SAPI — built-in, always available
                ps_script = (
                    f'Add-Type -AssemblyName System.Speech; '
                    f'$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$synth.Rate = 1; '
                    f'$synth.Speak("{text.replace(chr(34), chr(39))}")'
                )
                subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    timeout=30,
                )
                return
            except Exception as e:
                logger.debug("Windows SAPI failed: %s", e)

            # Try espeak on Windows (if installed)
            try:
                subprocess.run(
                    ["espeak", "-s", "150", text],
                    capture_output=True,
                    timeout=30,
                )
                return
            except FileNotFoundError:
                pass
        else:
            # Linux / macOS — try espeak
            try:
                subprocess.run(
                    ["espeak", "-s", "150", text],
                    capture_output=True,
                    timeout=30,
                )
                return
            except FileNotFoundError:
                pass

            # macOS fallback — built-in 'say' command
            if platform.system() == "Darwin":
                try:
                    subprocess.run(
                        ["say", text],
                        capture_output=True,
                        timeout=30,
                    )
                    return
                except FileNotFoundError:
                    pass

        logger.error(
            "No TTS fallback available. "
            "Linux: install espeak (sudo apt install espeak). "
            "Windows: SAPI should be built-in."
        )

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
