#!/bin/bash
# ============================================================
# HomePilot Installation Script for Raspberry Pi
# ============================================================
# This script:
# 1. Installs system dependencies
# 2. Creates a Python virtual environment
# 3. Installs Python packages
# 4. Downloads AI models (Vosk STT)
# 5. Creates required directories
# 6. Sets up the systemd service
#
# Usage:
#   chmod +x deploy/install.sh
#   sudo ./deploy/install.sh
# ============================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$INSTALL_DIR/venv"
MODEL_DIR="$INSTALL_DIR/models"
DATA_DIR="$INSTALL_DIR/data"
LOG_DIR="$INSTALL_DIR/logs"
ASSET_DIR="$INSTALL_DIR/assets/sounds"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║     HomePilot v2.0 — Installation Script            ║"
echo "║     Privacy-First Edge AI Voice Assistant            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: System Dependencies ──
echo -e "${GREEN}[1/6] Installing system dependencies...${NC}"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    portaudio19-dev \
    libsndfile1 \
    alsa-utils \
    espeak \
    ffmpeg \
    libasound2-dev \
    sox \
    wget \
    unzip

echo -e "  ${GREEN}✓ System dependencies installed.${NC}"

# ── Step 2: Python Virtual Environment ──
echo -e "${GREEN}[2/6] Creating Python virtual environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel -q
echo -e "  ${GREEN}✓ Virtual environment ready.${NC}"

# ── Step 3: Python Packages ──
echo -e "${GREEN}[3/6] Installing Python packages...${NC}"
pip install -r "$INSTALL_DIR/requirements.txt" -q
echo -e "  ${GREEN}✓ Python packages installed.${NC}"

# ── Step 4: Download AI Models ──
echo -e "${GREEN}[4/6] Downloading AI models...${NC}"
mkdir -p "$MODEL_DIR"

# Vosk STT Model (small English model ~40MB)
VOSK_MODEL="vosk-model-small-en-us-0.15"
if [ ! -d "$MODEL_DIR/$VOSK_MODEL" ]; then
    echo -e "  ${YELLOW}Downloading Vosk STT model ($VOSK_MODEL)...${NC}"
    wget -q -P /tmp "https://alphacephei.com/vosk/models/$VOSK_MODEL.zip"
    unzip -q -o "/tmp/$VOSK_MODEL.zip" -d "$MODEL_DIR"
    rm -f "/tmp/$VOSK_MODEL.zip"
    echo -e "  ${GREEN}✓ Vosk model downloaded.${NC}"
else
    echo -e "  ${GREEN}✓ Vosk model already present.${NC}"
fi

# Piper TTS Model
echo -e "  ${YELLOW}Note: Download a Piper TTS model manually:${NC}"
echo -e "  ${YELLOW}  https://github.com/rhasspy/piper/blob/master/VOICES.md${NC}"
echo -e "  ${YELLOW}  Recommended: en_US-lessac-medium${NC}"
echo -e "  ${YELLOW}  Place .onnx and .onnx.json files in $MODEL_DIR/${NC}"

# ── Step 5: Create Directories ──
echo -e "${GREEN}[5/6] Creating directories and assets...${NC}"
mkdir -p "$DATA_DIR" "$LOG_DIR" "$ASSET_DIR"
mkdir -p "$INSTALL_DIR/plugins"

# Create placeholder sound files using sox (if available)
if command -v sox &> /dev/null; then
    # Wake confirmation tone (short, pleasant beep)
    if [ ! -f "$ASSET_DIR/wake.wav" ]; then
        sox -n "$ASSET_DIR/wake.wav" synth 0.2 sine 880 vol 0.5 fade 0.05 0.2 0.05
    fi
    # Error tone (lower pitch)
    if [ ! -f "$ASSET_DIR/error.wav" ]; then
        sox -n "$ASSET_DIR/error.wav" synth 0.3 sine 330 vol 0.4 fade 0.05 0.3 0.1
    fi
    # Timer alert (repeating beep)
    if [ ! -f "$ASSET_DIR/timer_alert.wav" ]; then
        sox -n "$ASSET_DIR/timer_alert.wav" synth 0.15 sine 1000 vol 0.6 repeat 3
    fi
    echo -e "  ${GREEN}✓ Sound assets generated.${NC}"
else
    echo -e "  ${YELLOW}⚠ sox not available. Sound files not generated.${NC}"
fi

# Set ownership
chown -R pi:pi "$INSTALL_DIR"
echo -e "  ${GREEN}✓ Directories created.${NC}"

# ── Step 6: Install systemd Service ──
echo -e "${GREEN}[6/6] Installing systemd service...${NC}"
cp "$INSTALL_DIR/deploy/homepilot.service" /etc/systemd/system/homepilot.service
systemctl daemon-reload
systemctl enable homepilot.service
echo -e "  ${GREEN}✓ Service installed and enabled.${NC}"

# ── Done ──
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✅ HomePilot installation complete!${CYAN}                  ║"
echo -e "╠══════════════════════════════════════════════════════╣"
echo -e "║                                                      ║"
echo -e "║  ${NC}Next steps:${CYAN}                                         ║"
echo -e "║  ${NC}1. Edit config/default_config.yaml${CYAN}                   ║"
echo -e "║     ${NC}- Set your Picovoice access key${CYAN}                   ║"
echo -e "║     ${NC}- Configure Home Assistant (optional)${CYAN}             ║"
echo -e "║  ${NC}2. Download a Piper TTS voice model${CYAN}                  ║"
echo -e "║  ${NC}3. Start the service:${CYAN}                                ║"
echo -e "║     ${NC}sudo systemctl start homepilot${CYAN}                    ║"
echo -e "║  ${NC}4. Or run manually:${CYAN}                                  ║"
echo -e "║     ${NC}source venv/bin/activate${CYAN}                          ║"
echo -e "║     ${NC}python run.py${CYAN}                                     ║"
echo -e "║                                                      ║"
echo -e "╚══════════════════════════════════════════════════════╝${NC}"
echo ""
