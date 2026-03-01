"""
Audio input stream for HomePilot.

Captures PCM audio from the microphone in a background thread
and provides frames via a thread-safe queue for downstream
processing (wake word detection, STT, etc.).
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

import numpy as np

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import AudioConfig

logger = get_logger("homepilot.audio_input")


class AudioStream:
    """
    Threaded audio capture from the system microphone.

    Reads audio in fixed-size frames and places them on an
    internal queue. Consumers call `read_frame()` to get
    the next frame (blocking).

    Attributes:
        sample_rate: Audio sample rate in Hz.
        frame_length: Number of samples per frame.
        is_running: Whether the stream is actively capturing.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.sample_rate: int = config.sample_rate
        self.frame_length: int = config.frame_length
        self._device: int | None = config.input_device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self._stream: object | None = None
        self._thread: threading.Thread | None = None
        self.is_running: bool = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start capturing audio in a background thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="audio-capture",
        )
        self.is_running = True
        self._thread.start()
        logger.info(
            "Audio stream started (rate=%d, frame=%d, device=%s)",
            self.sample_rate,
            self.frame_length,
            self._device or "default",
        )

    def stop(self) -> None:
        """Stop the audio capture."""
        self._stop_event.set()
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        # Flush queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Audio stream stopped.")

    def read_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        """
        Read the next audio frame from the queue.

        Args:
            timeout: Max seconds to wait for a frame.

        Returns:
            Numpy array of int16 samples, or None on timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Discard all queued frames."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _capture_loop(self) -> None:
        """Internal capture loop — runs in background thread."""
        import sounddevice as sd

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.frame_length,
                device=self._device,
            ) as stream:
                logger.debug("Audio input device opened successfully.")
                while not self._stop_event.is_set():
                    data, overflowed = stream.read(self.frame_length)
                    if overflowed:
                        logger.warning("Audio input overflow detected.")
                    frame = data.flatten()
                    try:
                        self._queue.put_nowait(frame)
                    except queue.Full:
                        # Drop oldest frame to prevent stalling
                        try:
                            self._queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._queue.put_nowait(frame)
        except Exception as e:
            logger.error("Audio capture error: %s", e)
            self.is_running = False
