"""Configuration settings loader and validator."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Project root = two levels up from this file (homepilot/config/settings.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class WakeWordConfig:
    """Wake word detection settings."""
    engine: str = "porcupine"
    keyword: str = "jarvis"
    custom_keyword_path: str = ""
    sensitivity: float = 0.6
    access_key: str = ""


@dataclass
class AudioConfig:
    """Audio I/O settings."""
    input_device: int | None = None
    output_device: int | None = None
    sample_rate: int = 16000
    frame_length: int = 512
    vad_silence_timeout: float = 3.0
    max_record_seconds: float = 10.0
    noise_calibration_seconds: float = 1.0


@dataclass
class STTConfig:
    """Speech-to-text settings."""
    engine: str = "vosk"
    model_path: str = "models/vosk-model-small-en-us-0.15"


@dataclass
class TTSConfig:
    """Text-to-speech settings."""
    engine: str = "piper"
    model_path: str = "models/en_US-lessac-medium.onnx"
    config_path: str = "models/en_US-lessac-medium.onnx.json"
    speech_rate: float = 1.0
    volume: float = 0.8


@dataclass
class IntentConfig:
    """Intent engine settings."""
    confidence_threshold: float = 0.5
    fallback_response: str = "I'm sorry, I didn't understand that. Could you try again?"


@dataclass
class HomeAssistantConfig:
    """Home Assistant integration settings."""
    enabled: bool = False
    local_url: str = "http://homeassistant.local:8123"
    cloud_url: str = ""
    access_token: str = ""
    use_encrypted_token: bool = True
    verify_ssl: bool = False
    timeout: int = 10
    prefer_local: bool = True


@dataclass
class OSControlConfig:
    """OS command control settings."""
    enabled: bool = True
    allowed_apps: list[str] = field(default_factory=lambda: [
        # Cross-platform
        "firefox", "vlc", "code",
        # Linux
        "chromium-browser", "nautilus", "terminal",
        # Windows
        "chrome", "edge", "notepad", "calculator", "explorer",
        "powershell", "cmd",
    ])
    allowed_commands: list[str] = field(default_factory=lambda: [
        "shutdown", "reboot", "volume_up", "volume_down", "volume_mute",
        "system_status"
    ])
    require_confirmation: list[str] = field(default_factory=lambda: [
        "shutdown", "reboot"
    ])


@dataclass
class TimerConfig:
    """Timer system settings."""
    persistence_file: str = "data/timers.json"
    max_concurrent: int = 20
    alert_sound: str = "assets/sounds/timer_alert.wav"
    alert_repeat: int = 3


@dataclass
class SecurityConfig:
    """Security settings."""
    enable_command_validation: bool = True
    enable_rate_limiting: bool = True
    rate_limit_per_minute: int = 30
    token_encryption_key_file: str = "data/.keyfile"
    local_only_mode: bool = False
    enable_plugin_integrity: bool = True


@dataclass
class PluginConfig:
    """Plugin system settings."""
    enabled: bool = True
    plugin_dir: str = "plugins"
    enabled_plugins: list[str] = field(default_factory=list)
    manifest_file: str = "plugins/manifest.json"


@dataclass
class SoundsConfig:
    """Sound file paths."""
    wake_confirm: str = "assets/sounds/wake.wav"
    error: str = "assets/sounds/error.wav"
    timer_alert: str = "assets/sounds/timer_alert.wav"


@dataclass
class Settings:
    """
    Master settings container for HomePilot.

    Loads configuration from YAML file and provides typed access
    to all subsystem settings with sensible defaults.
    """
    assistant_name: str = "Jarvis"
    language: str = "en"
    log_level: str = "INFO"
    log_file: str = "logs/homepilot.log"

    wakeword: WakeWordConfig = field(default_factory=WakeWordConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    intent: IntentConfig = field(default_factory=IntentConfig)
    home_assistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    os_control: OSControlConfig = field(default_factory=OSControlConfig)
    timers: TimerConfig = field(default_factory=TimerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    plugins: PluginConfig = field(default_factory=PluginConfig)
    sounds: SoundsConfig = field(default_factory=SoundsConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Settings:
        """
        Load settings from YAML config + .env file.

        Priority: Environment variables > YAML config > dataclass defaults.
        Loads .env file from project root if present.
        """
        # Load .env file if it exists
        cls._load_env_file(PROJECT_ROOT / ".env")

        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "default_config.yaml"
        else:
            config_path = Path(config_path)

        data: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded

        settings = cls._from_dict(data)

        # Override with environment variables (highest priority)
        settings._apply_env_overrides()

        return settings

    @staticmethod
    def _load_env_file(env_path: Path) -> None:
        """
        Load variables from a .env file into os.environ.

        Only sets variables that are NOT already set in the
        environment, so real env vars always take priority.
        """
        if not env_path.exists():
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Only set if not already in environment
                if key and key not in os.environ:
                    os.environ[key] = value

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to settings."""
        env = os.environ.get

        # Picovoice
        if env("PICOVOICE_ACCESS_KEY"):
            self.wakeword.access_key = env("PICOVOICE_ACCESS_KEY", "")

        # Home Assistant
        if env("HA_ACCESS_TOKEN"):
            self.home_assistant.access_token = env("HA_ACCESS_TOKEN", "")
        if env("HA_LOCAL_URL"):
            self.home_assistant.local_url = env("HA_LOCAL_URL", "")
        if env("HA_CLOUD_URL"):
            self.home_assistant.cloud_url = env("HA_CLOUD_URL", "")

        # General
        if env("HOMEPILOT_LOG_LEVEL"):
            self.log_level = env("HOMEPILOT_LOG_LEVEL", "INFO")
        if env("HOMEPILOT_ASSISTANT_NAME"):
            self.assistant_name = env("HOMEPILOT_ASSISTANT_NAME", "Jarvis")
        if env("HOMEPILOT_LANGUAGE"):
            self.language = env("HOMEPILOT_LANGUAGE", "en")

        # Audio devices
        if env("AUDIO_INPUT_DEVICE"):
            try:
                self.audio.input_device = int(env("AUDIO_INPUT_DEVICE", ""))
            except ValueError:
                pass
        if env("AUDIO_OUTPUT_DEVICE"):
            try:
                self.audio.output_device = int(env("AUDIO_OUTPUT_DEVICE", ""))
            except ValueError:
                pass

        # Security
        if env("TOKEN_ENCRYPTION_KEY_FILE"):
            self.security.token_encryption_key_file = env(
                "TOKEN_ENCRYPTION_KEY_FILE", "data/.keyfile"
            )

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Settings:
        """Build Settings from a raw dict (parsed YAML)."""
        settings = cls(
            assistant_name=data.get("assistant_name", cls.assistant_name),
            language=data.get("language", cls.language),
            log_level=data.get("log_level", cls.log_level),
            log_file=data.get("log_file", cls.log_file),
        )
        # Map each sub-config from its dict
        _map = {
            "wakeword": (WakeWordConfig, "wakeword"),
            "audio": (AudioConfig, "audio"),
            "stt": (STTConfig, "stt"),
            "tts": (TTSConfig, "tts"),
            "intent": (IntentConfig, "intent"),
            "home_assistant": (HomeAssistantConfig, "home_assistant"),
            "os_control": (OSControlConfig, "os_control"),
            "timers": (TimerConfig, "timers"),
            "security": (SecurityConfig, "security"),
            "plugins": (PluginConfig, "plugins"),
            "sounds": (SoundsConfig, "sounds"),
        }
        for attr, (klass, key) in _map.items():
            sub_data = data.get(key, {})
            if isinstance(sub_data, dict):
                setattr(settings, attr, klass(**{
                    k: v for k, v in sub_data.items()
                    if k in klass.__dataclass_fields__
                }))
        return settings

    def resolve_path(self, relative: str) -> Path:
        """Resolve a path relative to the project root."""
        p = Path(relative)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p
