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

    Voice pipeline: Wake Word → STT → Agent.process() → TTS
    The Agent uses IntentParser for reliable tool selection and
    the LLM for JARVIS-style witty responses.
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

        # Agent system (JARVIS personality + tool execution)
        self._agent = None
        self._tool_router = None
        self._persistent_memory = None
        self._llm_engine = None

    def start(self) -> None:
        """
        Initialize all subsystems and start the main loop.

        This is the primary entry point. It blocks until
        shutdown is requested.
        """
        self._logger.info("=" * 60)
        self._logger.info("  HomePilot v2.1 — '%s' starting up", self.settings.assistant_name)
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
                farewell = self._agent.process("goodbye") if self._agent else "Goodbye!"
                self._tts_engine.speak_blocking(farewell)
            except Exception:
                pass
            self._tts_engine.shutdown()

        if self._persistent_memory:
            self._persistent_memory.close()

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
        # Try to initialize optional LLM engine (Ollama)
        self._llm_engine = None
        try:
            from homepilot.llm.llm_engine import LLMEngine
            llm = LLMEngine(
                model=s.agent.llm_model,
            )
            if llm.is_available():
                self._llm_engine = llm
                self._logger.info("🧠 LLM intelligence enabled (Ollama — %s)", s.agent.llm_model)
            else:
                self._logger.info("LLM not available — using regex/keyword/fuzzy matching")
        except Exception as e:
            self._logger.info("LLM not available: %s", e)

        self._intent_parser = IntentParser(
            confidence_threshold=s.intent.confidence_threshold,
            llm_engine=self._llm_engine,
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

        # ── Command Executor (kept for timer/plugin routing) ──
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

        # ── JARVIS Agent System ──
        self._logger.info("Initializing JARVIS agent system...")

        from homepilot.core.permissions import PermissionManager
        permissions = PermissionManager(
            permissions_path=s.resolve_path(s.permissions.permissions_file),
        )

        from homepilot.core.tool_router import ToolRouter
        self._tool_router = ToolRouter(permission_manager=permissions)

        # Register tools
        from homepilot.tools.system_tools import register_tools as reg_system
        reg_system(self._tool_router, system_controller=self._system_controller)

        from homepilot.tools.file_tools import register_tools as reg_file
        reg_file(self._tool_router)

        from homepilot.tools.dev_tools import register_tools as reg_dev
        reg_dev(self._tool_router)

        from homepilot.tools.home_assistant_tools import register_tools as reg_ha
        reg_ha(
            self._tool_router,
            ha_client=self._ha_client if s.home_assistant.enabled else None,
            event_loop=self._event_loop,
        )

        self._logger.info("📦 Registered %d tools", len(self._tool_router.list_tools()))

        # Persistent Memory
        from homepilot.core.memory import PersistentMemory
        self._persistent_memory = PersistentMemory(
            db_path=s.resolve_path(s.memory.database_path),
        )
        self._persistent_memory.ensure_user(s.user_name)

        # Planner
        from homepilot.core.planner import Planner
        planner = None
        if s.planner.enabled and self._llm_engine:
            planner = Planner(
                llm_generate=self._llm_engine.generate_response,
                max_steps=s.planner.max_steps,
            )

        # The Agent — heart of JARVIS
        from homepilot.core.agent import Agent
        self._agent = Agent(
            llm_engine=self._llm_engine,
            tool_router=self._tool_router,
            memory=self._persistent_memory,
            intent_parser=self._intent_parser,
            entity_resolver=self._entity_resolver,
            planner=planner,
            assistant_name=s.assistant_name,
            user_name=s.user_name,
            max_tool_iterations=s.agent.max_tool_iterations,
        )
        self._logger.info("🤖 JARVIS agent online")

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
        """Handle a wake word detection — process through JARVIS agent."""
        self._logger.info("🎤 Wake word detected! Entering command mode...")

        # Play confirmation sound
        wake_sound = self.settings.resolve_path(self.settings.sounds.wake_confirm)
        if wake_sound.exists():
            play_wav(str(wake_sound), device=self.settings.audio.output_device)
        else:
            # Speak a brief acknowledgment
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
                self._tts_engine.speak(
                    self._personality.idle_prompt()
                )
            return

        self._logger.info("📝 Transcript: '%s'", transcript)

        # ── Route through the JARVIS Agent ──
        # The Agent handles: intent parsing → tool execution → witty response
        response = self._agent.process(transcript)
        self._logger.info("💬 JARVIS: '%s'", response)

        # Store in short-term context memory too (for follow-ups)
        intent = self._intent_parser.parse(transcript)
        self._context_memory.add_turn(
            user_text=transcript,
            intent_name=intent.name,
            slots=intent.slots,
            response=response,
        )

        # Speak the response
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
    parser.add_argument(
        "-m", "--mode",
        type=str,
        choices=["voice", "cli"],
        default="voice",
        help="Run mode: 'voice' (full voice pipeline) or 'cli' (text agent)",
    )
    args = parser.parse_args()

    # Load settings
    settings = Settings.load(args.config)
    if args.verbose:
        settings.log_level = "DEBUG"

    if args.mode == "cli":
        _run_cli_mode(settings)
    else:
        # Default: voice mode (existing behavior)
        pilot = HomePilot(settings)
        pilot.start()


def _run_cli_mode(settings: Settings) -> None:
    """
    Run HomePilot in CLI agent mode.

    Initializes the LLM, tool system, memory, and planner,
    then starts the interactive CLI REPL.
    """
    from homepilot.utils.logger import setup_logger
    logger = setup_logger(
        name="homepilot",
        log_level=settings.log_level,
        log_file=str(settings.resolve_path(settings.log_file)),
    )

    logger.info("=" * 60)
    logger.info("  HomePilot v2.1 — '%s' CLI Agent Mode", settings.assistant_name)
    logger.info("=" * 60)

    # ── LLM Engine ──
    llm_engine = None
    try:
        from homepilot.llm.llm_engine import LLMEngine
        llm = LLMEngine(
            model=settings.agent.llm_model,
        )
        if llm.is_available():
            llm_engine = llm
            logger.info("🧠 LLM intelligence enabled (Ollama — %s)", settings.agent.llm_model)
        else:
            logger.warning("⚠️  Ollama not running — agent will have limited capabilities")
    except Exception as e:
        logger.warning("LLM not available: %s", e)

    # ── Permissions ──
    from homepilot.core.permissions import PermissionManager
    permissions = PermissionManager(
        permissions_path=settings.resolve_path(settings.permissions.permissions_file),
    )

    # ── Tool Router ──
    from homepilot.core.tool_router import ToolRouter
    router = ToolRouter(permission_manager=permissions)

    # ── Register System Tools ──
    from homepilot.os_control.system_commands import SystemController
    system_controller = SystemController(settings.os_control)

    from homepilot.tools.system_tools import register_tools as reg_system
    reg_system(router, system_controller=system_controller)

    # ── Register File Tools ──
    from homepilot.tools.file_tools import register_tools as reg_file
    reg_file(router)

    # ── Register Dev Tools ──
    from homepilot.tools.dev_tools import register_tools as reg_dev
    reg_dev(router)

    # ── Register Home Assistant Tools ──
    ha_client = None
    event_loop = None
    if settings.home_assistant.enabled:
        import asyncio
        from homepilot.home_assistant.ha_client import HomeAssistantClient
        ha_client = HomeAssistantClient(settings.home_assistant)

        event_loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(
            target=event_loop.run_forever,
            daemon=True,
            name="async-loop",
        )
        loop_thread.start()

        try:
            future = asyncio.run_coroutine_threadsafe(
                ha_client.connect(), event_loop,
            )
            connected = future.result(timeout=15)
            if connected:
                logger.info("Home Assistant connected.")
            else:
                logger.warning("Home Assistant connection failed.")
        except Exception as e:
            logger.warning("Home Assistant connection error: %s", e)

    from homepilot.tools.home_assistant_tools import register_tools as reg_ha
    reg_ha(router, ha_client=ha_client, event_loop=event_loop)

    logger.info("📦 Registered %d tools", len(router.list_tools()))

    # ── Persistent Memory ──
    from homepilot.core.memory import PersistentMemory
    memory = PersistentMemory(
        db_path=settings.resolve_path(settings.memory.database_path),
    )
    memory.ensure_user(settings.user_name)

    # ── Planner ──
    from homepilot.core.planner import Planner
    planner = None
    if settings.planner.enabled and llm_engine:
        planner = Planner(
            llm_generate=llm_engine.generate_response,
            max_steps=settings.planner.max_steps,
        )
        logger.info("📋 Task planner enabled")

    # ── Intent Parser & Entity Resolver ──
    # These are the "brains" — reliable intent detection via
    # regex/keyword/fuzzy/LLM matching. The Agent uses these
    # for tool selection and the LLM purely for personality.
    from homepilot.intent_engine.intent_parser import IntentParser
    from homepilot.entity_resolver.resolver import EntityResolver

    intent_parser = IntentParser(
        confidence_threshold=settings.intent.confidence_threshold,
        llm_engine=llm_engine,
    )
    entity_resolver = EntityResolver()
    logger.info("🎯 Intent parser ready (4-layer matching)")

    # ── Agent ──
    from homepilot.core.agent import Agent
    agent = Agent(
        llm_engine=llm_engine,
        tool_router=router,
        memory=memory,
        intent_parser=intent_parser,
        entity_resolver=entity_resolver,
        planner=planner,
        assistant_name=settings.assistant_name,
        user_name=settings.user_name,
        max_tool_iterations=settings.agent.max_tool_iterations,
    )

    # ── CLI Interface ──
    from homepilot.interfaces.cli import CLIInterface
    cli = CLIInterface(
        agent=agent,
        tool_router=router,
        memory=memory,
        assistant_name=settings.assistant_name,
        user_name=settings.user_name,
    )

    try:
        cli.run()
    except KeyboardInterrupt:
        pass
    finally:
        memory.close()
        if ha_client and event_loop:
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(
                    ha_client.close(), event_loop,
                ).result(timeout=5)
            except Exception:
                pass
            event_loop.call_soon_threadsafe(event_loop.stop)
        logger.info("HomePilot CLI agent shut down. Goodbye! 👋")


if __name__ == "__main__":
    main()

