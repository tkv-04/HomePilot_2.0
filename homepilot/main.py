"""
HomePilot — Privacy-First Edge AI Voice Assistant

Main orchestrator that initializes all modules and runs
the continuous listen → understand → execute → respond pipeline.

This is the heart of the system. It:
1. Loads configuration
2. Initializes all AI engines (wake word, STT, TTS)
3. Sets up command execution (OS, HA, timers)
4. Runs the main event loop:
   - Continuously listens for "Jarvis" wake word
   - On detection, records and transcribes speech
   - Parses intent & extracts entities
   - Executes command and speaks response
5. Handles graceful shutdown and crash recovery
"""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
import time
from pathlib import Path

from homepilot.audio_input.audio_stream import AudioStream
from homepilot.command_executor.executor import CommandExecutor
from homepilot.config.settings import Settings
from homepilot.entity_resolver.resolver import EntityResolver
from homepilot.home_assistant.ha_client import HomeAssistantClient
from homepilot.intent_engine.intent_parser import IntentParser
from homepilot.os_control.system_commands import SystemController
from homepilot.plugins.plugin_manager import PluginManager
from homepilot.security.validator import SecurityValidator
from homepilot.speech_to_text.stt_engine import STTEngine
from homepilot.timers.timer_manager import TimerManager
from homepilot.tts.tts_engine import TTSEngine
from homepilot.utils.audio_utils import play_wav
from homepilot.utils.context_memory import ContextMemory
from homepilot.utils.logger import setup_logger, get_logger
from homepilot.utils.personality import Personality
from homepilot.wakeword.detector import WakeWordDetector


class HomePilot:
    """
    Main application orchestrator for the HomePilot voice assistant.

    Manages the lifecycle of all subsystems and runs the
    continuous voice interaction loop.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._shutdown_event = threading.Event()

        # Initialize logger
        self._logger = setup_logger(
            name="homepilot",
            log_level=settings.log_level,
            log_file=str(settings.resolve_path(settings.log_file)),
        )

        # Subsystem instances (initialized in start())
        self._audio_stream: AudioStream | None = None
        self._wake_detector: WakeWordDetector | None = None
        self._stt_engine: STTEngine | None = None
        self._tts_engine: TTSEngine | None = None
        self._intent_parser: IntentParser | None = None
        self._entity_resolver: EntityResolver | None = None
        self._command_executor: CommandExecutor | None = None
        self._system_controller: SystemController | None = None
        self._ha_client: HomeAssistantClient | None = None
        self._timer_manager: TimerManager | None = None
        self._plugin_manager: PluginManager | None = None
        self._security_validator: SecurityValidator | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._context_memory = ContextMemory(max_turns=10)
        self._personality = Personality(name=settings.assistant_name)

    def start(self) -> None:
        """
        Initialize all subsystems and start the main loop.

        This is the primary entry point. It blocks until
        shutdown is requested.
        """
        self._logger.info("=" * 60)
        self._logger.info("  HomePilot v2.0 — '%s' starting up", self.settings.assistant_name)
        self._logger.info("=" * 60)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            self._initialize_subsystems()
            self._running = True
            self._logger.info(
                "✅ All systems online. Say '%s' to begin!",
                self.settings.wakeword.keyword.capitalize(),
            )
            self._main_loop()

        except KeyboardInterrupt:
            self._logger.info("Keyboard interrupt received.")
        except Exception as e:
            self._logger.critical("Fatal error: %s", e, exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully shut down all subsystems."""
        if not self._running:
            return
        self._running = False
        self._shutdown_event.set()

        self._logger.info("Shutting down HomePilot...")

        # Shutdown in reverse order
        if self._tts_engine:
            try:
                self._tts_engine.speak_blocking("Goodbye!")
            except Exception:
                pass
            self._tts_engine.shutdown()

        if self._timer_manager:
            self._timer_manager.stop()

        if self._plugin_manager:
            self._plugin_manager.unload_all()

        if self._audio_stream:
            self._audio_stream.stop()

        if self._wake_detector:
            self._wake_detector.cleanup()

        if self._stt_engine:
            self._stt_engine.cleanup()

        if self._ha_client and self._event_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._ha_client.close(), self._event_loop
                ).result(timeout=5)
            except Exception:
                pass

        if self._event_loop and self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

        self._logger.info("HomePilot shut down complete. Goodbye! 👋")

    def _initialize_subsystems(self) -> None:
        """Initialize all subsystems in dependency order."""
        s = self.settings

        # ── Security ──
        self._logger.info("Initializing security validator...")
        self._security_validator = SecurityValidator(s.security)

        # ── Audio Input ──
        self._logger.info("Initializing audio stream...")
        self._audio_stream = AudioStream(s.audio)

        # ── Wake Word ──
        self._logger.info("Initializing wake word detector...")
        self._wake_detector = WakeWordDetector(s.wakeword)
        self._wake_detector.initialize()

        # ── Speech-to-Text ──
        self._logger.info("Initializing STT engine...")
        self._stt_engine = STTEngine(s.stt, s.audio)
        self._stt_engine.initialize()

        # ── TTS ──
        self._logger.info("Initializing TTS engine...")
        self._tts_engine = TTSEngine(s.tts)
        self._tts_engine.initialize(output_device=s.audio.output_device)

        # ── Intent & Entity ──
        self._intent_parser = IntentParser(
            confidence_threshold=s.intent.confidence_threshold,
        )
        self._entity_resolver = EntityResolver()

        # ── OS Control ──
        self._system_controller = SystemController(s.os_control)

        # ── Home Assistant ──
        self._ha_client = HomeAssistantClient(s.home_assistant)
        if s.home_assistant.enabled:
            self._logger.info("Connecting to Home Assistant...")
            # Start async event loop in background thread
            self._event_loop = asyncio.new_event_loop()
            loop_thread = threading.Thread(
                target=self._event_loop.run_forever,
                daemon=True,
                name="async-loop",
            )
            loop_thread.start()
            # Connect HA client
            future = asyncio.run_coroutine_threadsafe(
                self._ha_client.connect(), self._event_loop,
            )
            try:
                connected = future.result(timeout=15)
                if connected:
                    self._logger.info("Home Assistant connected.")
                else:
                    self._logger.warning("Home Assistant connection failed.")
            except Exception as e:
                self._logger.warning("Home Assistant connection error: %s", e)

        # ── Timers ──
        self._timer_manager = TimerManager(
            persistence_file=str(s.resolve_path(s.timers.persistence_file)),
            max_concurrent=s.timers.max_concurrent,
            on_expire=self._on_timer_expire,
        )
        self._timer_manager.start()

        # ── Plugins ──
        if s.plugins.enabled:
            self._plugin_manager = PluginManager(
                plugin_dir=str(s.resolve_path(s.plugins.plugin_dir)),
                enabled_plugins=s.plugins.enabled_plugins,
                manifest_file=str(s.resolve_path(s.plugins.manifest_file)),
                check_integrity=s.security.enable_plugin_integrity,
            )
            self._plugin_manager.load_plugins()

        # ── Command Executor ──
        self._command_executor = CommandExecutor(
            system_controller=self._system_controller,
            ha_client=self._ha_client if s.home_assistant.enabled else None,
            timer_manager=self._timer_manager,
            plugin_manager=self._plugin_manager,
            security_validator=self._security_validator,
            assistant_name=s.assistant_name,
        )
        if self._event_loop:
            self._command_executor.set_event_loop(self._event_loop)

        # ── Start Audio ──
        self._audio_stream.start()

    def _main_loop(self) -> None:
        """
        Main voice interaction loop.

        Continuously:
        1. Listen for the wake word
        2. On detection, record speech
        3. Transcribe, parse intent, execute, respond
        """
        while self._running and not self._shutdown_event.is_set():
            try:
                # Read an audio frame
                frame = self._audio_stream.read_frame(timeout=1.0)
                if frame is None:
                    continue

                # Check for wake word
                # Porcupine may require a different frame length
                if len(frame) != self._wake_detector.frame_length:
                    continue

                if self._wake_detector.process(frame):
                    self._handle_wake()

            except Exception as e:
                self._logger.error("Main loop error: %s", e, exc_info=True)
                time.sleep(1.0)  # Prevent tight error loops

    def _handle_wake(self) -> None:
        """Handle a wake word detection event."""
        self._logger.info("🎤 Wake word detected! Entering command mode...")

        # Play confirmation sound
        wake_sound = self.settings.resolve_path(self.settings.sounds.wake_confirm)
        if wake_sound.exists():
            play_wav(str(wake_sound), device=self.settings.audio.output_device)
        else:
            # Speak a brief acknowledgment using personality
            if self._tts_engine:
                self._tts_engine.speak_blocking(self._personality.acknowledge())

        # Drain any buffered audio
        self._audio_stream.drain()

        # Transcribe user speech
        self._logger.info("Listening for command...")
        transcript = self._stt_engine.transcribe(self._audio_stream)

        if not transcript:
            self._logger.info("No speech detected. Returning to listen mode.")
            if self._tts_engine:
                self._tts_engine.speak(self._personality.idle_prompt())
            return

        self._logger.info("📝 Transcript: '%s'", transcript)

        # Parse intent
        intent = self._intent_parser.parse(transcript)
        self._logger.info(
            "🎯 Intent: %s (confidence=%.2f)",
            intent.name, intent.confidence,
        )

        # Resolve entities — use context memory for follow-ups
        entities = self._entity_resolver.resolve(intent.name, intent.slots)

        # Fill missing device/room from conversation context
        if not entities.device_name and self._context_memory.last_device:
            entities.device_name = self._context_memory.last_device
            self._logger.debug("Using device from context: %s", entities.device_name)
        if not entities.room and self._context_memory.last_room:
            entities.room = self._context_memory.last_room

        # Execute command
        response = self._command_executor.execute(intent, entities)
        self._logger.info("💬 Response: '%s'", response)

        # Store in conversation memory
        self._context_memory.add_turn(
            user_text=transcript,
            intent_name=intent.name,
            slots=intent.slots,
            response=response,
        )

        # Speak response
        if self._tts_engine and response:
            self._tts_engine.speak(response)

    def _on_timer_expire(self, timer) -> None:
        """Callback when a timer expires."""
        message = timer.message or f"Your {timer.name} has finished."
        self._logger.info("⏰ Timer expired: %s", message)

        # Play alert sound
        alert_path = self.settings.resolve_path(self.settings.sounds.timer_alert)
        if alert_path.exists():
            play_wav(str(alert_path), device=self.settings.audio.output_device)

        # Speak the alert with personality
        if self._tts_engine:
            announcement = self._personality.timer_alert(message)
            self._tts_engine.speak(announcement, priority=True)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        self._logger.info("Received signal %d. Initiating shutdown...", signum)
        self._running = False
        self._shutdown_event.set()


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="HomePilot — Privacy-First Edge AI Voice Assistant",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Load settings
    settings = Settings.load(args.config)
    if args.verbose:
        settings.log_level = "DEBUG"

    # Create and run
    pilot = HomePilot(settings)
    pilot.start()


if __name__ == "__main__":
    main()
