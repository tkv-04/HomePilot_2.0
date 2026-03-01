# HomePilot Setup Guide

## Prerequisites

| Item | Minimum | Recommended |
|------|---------|-------------|
| Raspberry Pi | 4 (2GB) | 4 (4GB+) |
| Microphone | USB mic | ReSpeaker array |
| Speaker | 3.5mm | USB DAC + speaker |
| Storage | 8GB SD | 32GB+ SD |
| Python | 3.11+ | 3.12 |
| OS | Raspberry Pi OS Lite | Raspberry Pi OS (64-bit) |

## Step 1: Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Flash **Raspberry Pi OS (64-bit)** to your SD card
3. Enable SSH in the imager settings
4. Boot and SSH into your Pi

## Step 2: System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Verify Python 3.11+
python3 --version

# Install git
sudo apt install -y git
```

## Step 3: Clone & Install HomePilot

```bash
cd ~
git clone <your-repo-url> HomePilot_2.0
cd HomePilot_2.0

# Run automated installer
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

This installs:
- System deps (portaudio, alsa, espeak, sox)
- Python venv + all packages
- Vosk STT model (~40MB)
- systemd service
- Sound effect assets

## Step 4: Get API Keys

### Picovoice Access Key (Required)

1. Go to [console.picovoice.ai](https://console.picovoice.ai)
2. Create a free account
3. Copy your **Access Key**
4. Add to config:

```yaml
wakeword:
  access_key: "YOUR_ACCESS_KEY_HERE"
```

## Step 5: Download Piper TTS Voice

```bash
cd ~/HomePilot_2.0/models

# Download recommended voice
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/voice-en_US-lessac-medium.tar.gz
tar -xzf voice-en_US-lessac-medium.tar.gz
rm voice-en_US-lessac-medium.tar.gz
```

Update the config if needed:
```yaml
tts:
  model_path: "models/en_US-lessac-medium.onnx"
  config_path: "models/en_US-lessac-medium.onnx.json"
```

## Step 6: Configure

```bash
nano ~/HomePilot_2.0/config/default_config.yaml
```

Key settings to review:
- `wakeword.access_key` — **required**
- `audio.input_device` / `output_device` — set if not using defaults
- `home_assistant.*` — if you have HA

### Find Audio Devices

```bash
# List input devices
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

## Step 7: Test Run

```bash
cd ~/HomePilot_2.0
source venv/bin/activate
python run.py -v  # Verbose mode
```

Say **"Jarvis"** and issue a command like:
- "What time is it?"
- "Set a timer for 5 minutes"
- "What's the system status?"

## Step 8: Deploy as Service

```bash
# Start
sudo systemctl start homepilot

# Enable auto-start on boot
sudo systemctl enable homepilot

# Check status
sudo systemctl status homepilot

# View logs
journalctl -u homepilot -f
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No microphone detected | Run `arecord -l` to list devices. Set `audio.input_device` in config. |
| Wake word not responding | Check Picovoice access key. Increase `wakeword.sensitivity`. |
| STT returns empty | Verify Vosk model path. Check mic volume with `alsamixer`. |
| No audio output | Run `speaker-test -t wav`. Check `audio.output_device` in config. |
| Permission denied | Ensure user is in `audio` group: `sudo usermod -aG audio pi` |
