# HomePilot 2.0

**Privacy-First Edge AI Voice Assistant**

A fully local, offline-first voice assistant optimized for Raspberry Pi,
with Home Assistant integration. All AI processing runs on-device — no cloud required.

## ✨ Features

- 🎤 **Wake Word Detection** — "Jarvis" via Picovoice Porcupine
- 🗣️ **Offline Speech-to-Text** — Vosk real-time transcription
- 🧠 **Intent Understanding** — Rule-based NLU with entity extraction
- 🔊 **Neural Text-to-Speech** — Piper TTS for natural voice output
- 🏠 **Home Assistant Integration** — Control lights, sensors, scenes
- ⏱️ **Timer System** — Multiple concurrent timers with voice alerts
- 💻 **OS Control** — Launch apps, control volume, system status
- 🔒 **Security-First** — Whitelisted commands, encrypted tokens, input sanitization
- 🧩 **Plugin System** — Extensible skill architecture with integrity checking

## 🚀 Quick Start

### On Raspberry Pi

```bash
# Clone the repository
git clone <repo-url> ~/HomePilot_2.0
cd ~/HomePilot_2.0

# Run the installer
chmod +x deploy/install.sh
sudo ./deploy/install.sh

# Edit your configuration
nano config/default_config.yaml
# → Set your Picovoice access key
# → Configure Home Assistant (optional)

# Start the assistant
source venv/bin/activate
python run.py
```

### As a System Service

```bash
sudo systemctl start homepilot
sudo systemctl status homepilot
journalctl -u homepilot -f  # View logs
```

## 📁 Project Structure

```
HomePilot_2.0/
├── run.py                  # Entry point
├── config/
│   └── default_config.yaml # Master configuration
├── homepilot/
│   ├── main.py             # Main orchestrator
│   ├── audio_input/        # Microphone capture
│   ├── wakeword/           # Wake word detection
│   ├── speech_to_text/     # Vosk STT engine
│   ├── intent_engine/      # Intent classification
│   ├── entity_resolver/    # Entity normalization
│   ├── command_executor/   # Command dispatch
│   ├── os_control/         # System commands
│   ├── home_assistant/     # HA REST API client
│   ├── timers/             # Timer management
│   ├── tts/                # Piper TTS engine
│   ├── security/           # Validation & encryption
│   ├── plugins/            # Plugin system
│   └── utils/              # Logging & audio tools
├── deploy/
│   ├── homepilot.service   # systemd unit file
│   └── install.sh          # Raspberry Pi installer
├── models/                 # AI model files
├── plugins/                # Custom skill plugins
├── docs/                   # Documentation
└── assets/sounds/          # Audio assets
```

## 📖 Documentation

- [Setup Guide](docs/SETUP.md)
- [Security Hardening](docs/SECURITY.md)
- [Home Assistant Integration](docs/HOME_ASSISTANT.md)
- [Wake Word Customization](docs/WAKE_WORD.md)
- [Performance Tuning](docs/PERFORMANCE.md)

## 🔑 Requirements

- Raspberry Pi 4 (2GB+ RAM) or newer
- USB microphone
- Speaker (3.5mm or USB)
- Python 3.11+
- Picovoice access key (free at [console.picovoice.ai](https://console.picovoice.ai))

## 📄 License

MIT License
