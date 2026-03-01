# HomePilot Setup Guide

## Prerequisites

### Linux (Raspberry Pi)

| Item | Minimum | Recommended |
|------|---------|-------------|
| Device | Raspberry Pi 4 (2GB) | RPi 4 (4GB+) or x86 |
| Microphone | USB mic | ReSpeaker array |
| Speaker | 3.5mm | USB DAC + speaker |
| Storage | 8GB SD | 32GB+ SD |
| Python | 3.11+ | 3.12 |
| OS | Raspberry Pi OS Lite | RPi OS 64-bit |

### Windows

| Item | Minimum | Recommended |
|------|---------|-------------|
| OS | Windows 10 | Windows 11 |
| Microphone | Built-in / USB | USB mic |
| Speaker | Built-in | External speaker |
| Python | 3.11+ | 3.12 |

---

## Linux Installation

### Step 1: System Setup

```bash
sudo apt update && sudo apt upgrade -y
python3 --version  # Verify 3.11+
sudo apt install -y git
```

### Step 2: Clone & Install

```bash
cd ~
git clone <your-repo-url> HomePilot_2.0
cd HomePilot_2.0

chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

This installs system deps (portaudio, alsa, espeak, sox), creates a venv, downloads the Vosk STT model, generates sound effects, and installs the systemd service.

### Step 3: Run as Service

```bash
sudo systemctl start homepilot
sudo systemctl enable homepilot   # Auto-start on boot
journalctl -u homepilot -f        # View logs
```

---

## Windows Installation

### Step 1: Install Python

Download Python 3.11+ from [python.org](https://www.python.org/downloads/). During install, check **"Add python.exe to PATH"**.

### Step 2: Clone & Install

```powershell
git clone <your-repo-url> HomePilot_2.0
cd HomePilot_2.0

.\deploy\install.ps1
```

This creates a venv, installs Python packages, and downloads the Vosk STT model.

### Step 3: Run

```powershell
.\venv\Scripts\activate
python run.py -v
```

---

## Common Steps (Both Platforms)

### Get a Picovoice Access Key (Required)

1. Go to [console.picovoice.ai](https://console.picovoice.ai)
2. Create a free account
3. Copy your **Access Key**
4. Add to `config/default_config.yaml`:

```yaml
wakeword:
  access_key: "YOUR_ACCESS_KEY_HERE"
```

### Download Piper TTS Voice

**Linux:**
```bash
cd ~/HomePilot_2.0/models
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/voice-en_US-lessac-medium.tar.gz
tar -xzf voice-en_US-lessac-medium.tar.gz && rm voice-en_US-lessac-medium.tar.gz
```

**Windows:**
Download manually from the [Piper Voices page](https://github.com/rhasspy/piper/blob/master/VOICES.md) and place the `.onnx` + `.onnx.json` files in the `models/` directory.

> **Note:** If Piper is not installed, HomePilot will automatically fall back to **espeak** (Linux) or **Windows SAPI** (Windows built-in TTS).

### Find Audio Devices

```python
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Set the device index in config if not using defaults:
```yaml
audio:
  input_device: 1
  output_device: 3
```

### Test Run

```bash
python run.py -v   # Verbose mode
```

Say **"Jarvis"** and try:
- "What time is it?"
- "Set a timer for 5 minutes"
- "What's the system status?"
- "Open Firefox"

---

## Troubleshooting

| Issue | Platform | Solution |
|-------|----------|----------|
| No microphone detected | Both | Run `python -c "import sounddevice; print(sounddevice.query_devices())"` and set `audio.input_device` |
| Wake word not responding | Both | Check Picovoice access key. Increase `wakeword.sensitivity` |
| STT returns empty | Both | Verify Vosk model path. Check mic volume |
| No audio output | Linux | Run `speaker-test -t wav`. Check `audio.output_device` |
| No audio output | Windows | Check Windows sound settings. Try a different `output_device` |
| Permission denied | Linux | Add user to audio group: `sudo usermod -aG audio pi` |
| Volume control fails | Windows | Install [nircmd](https://www.nirsoft.net/utils/nircmd.html) for reliable volume control, or the PowerShell fallback is used automatically |
