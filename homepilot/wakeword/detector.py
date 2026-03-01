"""
Wake word detection engine for HomePilot.

Uses Picovoice Porcupine for low-CPU, always-on "Jarvis"
detection. Supports built-in keywords and custom .ppn files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import WakeWordConfig

logger = get_logger("homepilot.wakeword")


class WakeWordDetector:
    """
    Porcupine-based wake word detector.

    Processes audio frames and returns True when the wake word
    ("Jarvis" by default) is detected.

    Usage:
        detector = WakeWordDetector(config)
        detector.initialize()
        ...
        if detector.process(audio_frame):
            print("Wake word detected!")
        ...
        detector.cleanup()
    """

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config
        self._porcupine: object | None = None
        self.frame_length: int = 0
        self.sample_rate: int = 0

    def initialize(self) -> None:
        """
        Initialize the Porcupine wake word engine.

        Requires a valid Picovoice access key (free at console.picovoice.ai).
        """
        import pvporcupine

        access_key = self._config.access_key
        if not access_key:
            raise ValueError(
                "Picovoice access key is required. "
                "Get a free key at https://console.picovoice.ai "
                "and set it in config/default_config.yaml under wakeword.access_key"
            )

        # Use custom keyword file or built-in keyword
        keyword_paths = None
        keywords = None
        if self._config.custom_keyword_path:
            kw_path = Path(self._config.custom_keyword_path)
            if not kw_path.exists():
                raise FileNotFoundError(
                    f"Custom keyword file not found: {kw_path}"
                )
            keyword_paths = [str(kw_path)]
            logger.info("Using custom wake word: %s", kw_path.stem)
        else:
            keywords = [self._config.keyword]
            logger.info("Using built-in wake word: '%s'", self._config.keyword)

        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=keywords,
            keyword_paths=keyword_paths,
            sensitivities=[self._config.sensitivity],
        )

        self.frame_length = self._porcupine.frame_length
        self.sample_rate = self._porcupine.sample_rate

        logger.info(
            "Porcupine initialized (frame_length=%d, sample_rate=%d, sensitivity=%.2f)",
            self.frame_length,
            self.sample_rate,
            self._config.sensitivity,
        )

    def process(self, audio_frame: np.ndarray) -> bool:
        """
        Process a single audio frame for wake word detection.

        Args:
            audio_frame: Numpy array of int16 PCM samples.
                         Must be exactly `self.frame_length` samples.

        Returns:
            True if the wake word was detected, False otherwise.
        """
        if self._porcupine is None:
            raise RuntimeError("WakeWordDetector not initialized. Call initialize() first.")

        # Porcupine expects a list or array of int16
        pcm = audio_frame.tolist() if isinstance(audio_frame, np.ndarray) else audio_frame
        result = self._porcupine.process(pcm)

        if result >= 0:
            logger.info("🎯 Wake word detected! (keyword_index=%d)", result)
            return True
        return False

    def cleanup(self) -> None:
        """Release Porcupine resources."""
        if self._porcupine is not None:
            self._porcupine.delete()
            self._porcupine = None
            logger.info("Porcupine wake word engine released.")
