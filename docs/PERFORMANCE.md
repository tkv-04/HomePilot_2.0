# Performance Optimization Guide

## Resource Benchmarks (Raspberry Pi 4, 4GB)

| Component | CPU | RAM | Latency |
|-----------|-----|-----|---------|
| Wake word (Porcupine) | ~1% | ~5 MB | <10ms |
| STT (Vosk small model) | ~30% peak | ~80 MB | ~1s for 3s audio |
| TTS (Piper medium) | ~40% peak | ~100 MB | ~200ms |
| Idle (listening) | ~3% | ~150 MB total | — |

## Optimization Tips

### 1. Use the Small Vosk Model
```yaml
stt:
  model_path: "models/vosk-model-small-en-us-0.15"  # ~40MB, fast
```
The large model (1.8GB) gives better accuracy but is slower on RPi.

### 2. Reduce Audio Frame Size
Smaller frames = more responsive wake word but slightly higher CPU:
```yaml
audio:
  frame_length: 512    # Default, good balance
  # frame_length: 256  # More responsive but higher CPU
```

### 3. Tune Silence Timeout
Reduce the silence timeout for faster command completion:
```yaml
audio:
  vad_silence_timeout: 2.0  # Default: 3.0 — reducing speeds up response
  max_record_seconds: 8     # Default: 10
```

### 4. TTS Voice Selection
Lighter voices for faster synthesis:
- `en_US-lessac-low` — fastest, ~100ms
- `en_US-lessac-medium` — balanced, ~200ms (recommended)
- `en_US-lessac-high` — best quality, ~400ms

### 5. Disable Unused Modules
```yaml
home_assistant:
  enabled: false       # If not using HA
plugins:
  enabled: false       # If not using plugins
```

### 6. CPU Governor
Set the CPU governor to `performance` for consistent latency:
```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### 7. Memory Management
- Use 64-bit Raspberry Pi OS for efficient memory use
- Reduce GPU memory: `sudo raspi-config` → Performance → GPU Memory → 16MB
- Add swap if needed: `sudo dphys-swapfile setup && sudo dphys-swapfile swapon`

### 8. Audio Optimization
- Use a USB audio adapter instead of the 3.5mm jack for lower latency
- Set ALSA buffer sizes:
  ```bash
  # In /etc/asound.conf
  pcm.!default {
      type hw
      card 1
      format S16_LE
      rate 16000
      period_size 512
      buffer_size 4096
  }
  ```

## Monitoring Performance

```bash
# Real-time system stats
htop

# CPU temperature
vcgencmd measure_temp

# HomePilot logs
journalctl -u homepilot -f

# Memory usage
free -h
```

## Performance Goals Summary

| Metric | Target | Achievable |
|--------|--------|------------|
| Wake-to-response | < 2s | ✅ ~1.5s typical |
| CPU idle | < 5% | ✅ ~3% |
| RAM total | < 300MB | ✅ ~150-200MB |
| 24/7 stability | Weeks | ✅ With crash recovery |
