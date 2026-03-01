# Performance Optimization Guide

## Resource Benchmarks

### Raspberry Pi 4 (4GB)

| Component | CPU | RAM | Latency |
|-----------|-----|-----|---------|
| Wake word (Porcupine) | ~1% | ~5 MB | <10ms |
| STT (Vosk small model) | ~30% peak | ~80 MB | ~1s for 3s audio |
| TTS (Piper medium) | ~40% peak | ~100 MB | ~200ms |
| Idle (listening) | ~3% | ~150 MB total | — |

### Windows Desktop (Typical)

| Component | CPU | RAM | Latency |
|-----------|-----|-----|---------|
| Wake word (Porcupine) | <1% | ~5 MB | <5ms |
| STT (Vosk small model) | ~10% peak | ~80 MB | <0.5s |
| TTS (Piper medium) | ~15% peak | ~100 MB | ~100ms |
| TTS (Windows SAPI fallback) | ~5% | ~10 MB | ~300ms |
| Idle (listening) | ~1% | ~120 MB total | — |

## Optimization Tips

### 1. Choose the Right Vosk Model
```yaml
stt:
  model_path: "models/vosk-model-small-en-us-0.15"  # ~40MB, fast
```
The large model (1.8GB) gives better accuracy but is slower, especially on RPi.

### 2. Tune Silence Timeout
Reduce for faster command completion:
```yaml
audio:
  vad_silence_timeout: 2.0  # Default 3.0
  max_record_seconds: 8     # Default 10
```

### 3. TTS Voice Selection
| Voice | Latency (RPi) | Latency (Windows) |
|-------|---------------|-------------------|
| `en_US-lessac-low` | ~100ms | ~50ms |
| `en_US-lessac-medium` | ~200ms | ~100ms |
| `en_US-lessac-high` | ~400ms | ~200ms |

### 4. Disable Unused Modules
```yaml
home_assistant:
  enabled: false
plugins:
  enabled: false
```

### 5. Platform-Specific Tuning

**Linux (Raspberry Pi):**
```bash
# Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Reduce GPU memory
sudo raspi-config  # → Performance → GPU Memory → 16MB

# ALSA buffer optimization
# /etc/asound.conf:
# pcm.!default { type hw; card 1; period_size 512; buffer_size 4096 }
```

**Windows:**
```powershell
# Set power plan to High Performance
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c

# Disable unnecessary audio enhancements
# Settings → Sound → Device Properties → Disable Enhancements
```

## Monitoring Performance

**Linux:**
```bash
htop                       # Real-time stats
vcgencmd measure_temp      # CPU temperature (RPi)
journalctl -u homepilot -f # HomePilot logs
free -h                    # Memory
```

**Windows:**
```powershell
taskmgr                    # Task Manager
Get-Process python | Select CPU, WorkingSet  # Python resource usage
Get-Content logs\homepilot.log -Tail 20      # Recent logs
```

## Performance Goals

| Metric | Target | RPi 4 | Windows Desktop |
|--------|--------|-------|-----------------|
| Wake-to-response | < 2s | ~1.5s | ~0.8s |
| CPU idle | < 5% | ~3% | ~1% |
| RAM total | < 300MB | ~150-200MB | ~120-150MB |
| 24/7 stability | Weeks | ✅ | ✅ |
