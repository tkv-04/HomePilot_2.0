# HomePilot 2.0

**Privacy-First Edge AI Voice Assistant**

A fully local, offline-first voice assistant with cross-platform support (Linux & Windows).
All AI processing runs on-device — no cloud required.

## ✨ Features

- 🎤 **Wake Word Detection** — "Jarvis" via Picovoice Porcupine
- 🗣️ **Offline Speech-to-Text** — Vosk real-time transcription
- 🧠 **Intent Understanding** — Rule-based NLU with 18 intent patterns & entity extraction
- 🔊 **Neural Text-to-Speech** — Piper TTS (Linux/Windows), Windows SAPI fallback, espeak fallback
- 🏠 **Home Assistant Integration** — Control lights, sensors, scenes via local API + Nabu Casa
- ⏱️ **Timer System** — Multiple concurrent timers with voice alerts & persistence
- 💻 **OS Control** — Launch apps, control volume, system status (platform-aware)
- 🔒 **Security-First** — Whitelisted commands, encrypted tokens, input sanitization, rate limiting
- 🧩 **Plugin System** — Extensible skill architecture with SHA256 integrity checking
- 💬 **Context Memory** — Multi-turn conversation tracking for follow-up commands
- 🎭 **Personality Engine** — Natural, varied responses with time-aware greetings

## 🖥️ Platform Support

| Feature | Linux (Raspberry Pi) | Windows |
|---------|---------------------|---------|
| Wake word | ✅ Porcupine | ✅ Porcupine |
| STT | ✅ Vosk | ✅ Vosk |
| TTS | ✅ Piper / espeak | ✅ Piper / Windows SAPI |
| Volume | ✅ ALSA (amixer) | ✅ nircmd / PowerShell |
| Shutdown/Reboot | ✅ sudo shutdown | ✅ shutdown.exe |
| App launching | ✅ shutil.which | ✅ shutil.which + startfile |
| Service | ✅ systemd | ⚙️ Task Scheduler / NSSM |
| Install | ✅ install.sh | ✅ install.ps1 |

## 🚀 Quick Start

### On Raspberry Pi (Linux)

```bash
git clone https://github.com/tkv-04/HomePilot_2.0 ~/HomePilot_2.0
cd ~/HomePilot_2.0

chmod +x deploy/install.sh
sudo ./deploy/install.sh

nano config/default_config.yaml  # Set your Picovoice access key

source venv/bin/activate
python run.py
```

### On Windows

```powershell
git clone https://github.com/tkv-04/HomePilot_2.0
cd HomePilot_2.0

.\deploy\install.ps1

# Edit config\default_config.yaml — set your Picovoice access key

.\venv\Scripts\activate
python run.py
```

### As a Linux Service

```bash
sudo systemctl start homepilot
sudo systemctl status homepilot
journalctl -u homepilot -f
```

## 📁 Project Structure

```
HomePilot_2.0/
├── run.py                      # Entry point
├── config/
│   └── default_config.yaml     # Master configuration
├── homepilot/
│   ├── main.py                 # Main orchestrator
│   ├── audio_input/            # Microphone capture
│   ├── wakeword/               # Wake word detection (Porcupine)
│   ├── speech_to_text/         # Vosk STT engine
│   ├── intent_engine/          # Intent classification (18 patterns)
│   ├── entity_resolver/        # Entity normalization
│   ├── command_executor/       # Command dispatch (18 handlers)
│   ├── os_control/             # System commands (cross-platform)
│   ├── home_assistant/         # HA REST API client
│   ├── timers/                 # Timer management
│   ├── tts/                    # TTS engine (cross-platform)
│   ├── security/               # Validation & encryption
│   ├── plugins/                # Plugin system
│   ├── edge_ai_models/         # Model management
│   └── utils/                  # Logger, audio, context, personality
├── deploy/
│   ├── homepilot.service       # systemd unit (Linux)
│   ├── install.sh              # Linux installer
│   └── install.ps1             # Windows installer
├── plugins/                    # Custom skill plugins
│   └── example_weather.py      # Example plugin
├── models/                     # AI model files
├── docs/                       # Documentation
└── assets/sounds/              # Audio assets
```

## 📖 Documentation

- [Setup Guide](docs/SETUP.md) — Step-by-step installation
- [Security Hardening](docs/SECURITY.md) — Security architecture & recommendations
- [Home Assistant](docs/HOME_ASSISTANT.md) — HA integration setup
- [Wake Word](docs/WAKE_WORD.md) — Custom wake word training
- [Performance](docs/PERFORMANCE.md) — RPi optimization & benchmarks

## 🔑 Requirements

- **Linux:** Raspberry Pi 4 (2GB+ RAM) or any x86 machine
- **Windows:** Windows 10/11
- USB microphone + speaker
- Python 3.11+
- Picovoice access key (free at [console.picovoice.ai](https://console.picovoice.ai))

## 📄 License

MIT License
