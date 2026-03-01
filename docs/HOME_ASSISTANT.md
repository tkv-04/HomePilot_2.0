# Home Assistant Integration Guide

## Overview

HomePilot integrates with Home Assistant via the REST API on both Linux and Windows. It supports:
- Controlling lights, switches, fans, locks
- Querying sensor values
- Running scenes and automations
- Local API (preferred) with Nabu Casa cloud fallback

## Setup

### 1. Create a Long-Lived Access Token

1. Open Home Assistant web UI
2. Go to your **Profile** (bottom-left)
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**, name it "HomePilot"
5. Copy the token

### 2. Configure HomePilot

Edit `config/default_config.yaml`:

```yaml
home_assistant:
  enabled: true
  local_url: "http://192.168.1.100:8123"  # Your HA IP
  access_token: "YOUR_LONG_LIVED_TOKEN"
  prefer_local: true
  timeout: 10
```

### 3. Encrypted Token Storage (Recommended)

Instead of plaintext config, store the token encrypted:

**Linux:**
```bash
source venv/bin/activate
python -c "
from homepilot.security.token_store import TokenStore
store = TokenStore('data/.keyfile')
store.store_token('ha_token', 'YOUR_LONG_LIVED_TOKEN')
print('Token stored securely.')
"
```

**Windows:**
```powershell
.\venv\Scripts\activate
python -c "from homepilot.security.token_store import TokenStore; store = TokenStore('data/.keyfile'); store.store_token('ha_token', 'YOUR_LONG_LIVED_TOKEN'); print('Token stored.')"
```

Then set `use_encrypted_token: true` in config and leave `access_token` empty.

## Voice Commands

| Command | Example |
|---------|---------|
| Device control | "Turn on the kitchen light" |
| Brightness | "Set the living room light to 50 percent" |
| Sensors | "What's the temperature?" |
| Scenes | "Activate movie night scene" |
| Automations | "Run the goodnight automation" |

## Nabu Casa Cloud Fallback

```yaml
home_assistant:
  cloud_url: "https://your-instance.ui.nabu.casa"
  prefer_local: true   # Tries local first
```

HomePilot automatically falls back to the cloud URL if the local API is unreachable. Works identically on Linux and Windows.

## Entity Naming Tips

- Use clear **friendly names** in HA (e.g., "Kitchen Light" not "light.switch_relay_7c")
- Keep names unique per room
- Voice commands support partial matching

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Not connected to HA" | Verify URL is reachable: `curl http://IP:8123/api/` (Linux) or `Invoke-WebRequest http://IP:8123/api/` (Windows) |
| "Entity not found" | Check entity naming in HA Developer Tools → States |
| Cloud fallback fails | Verify Nabu Casa subscription and `cloud_url` |
| Timeout errors | Increase `timeout` value. Check network connectivity |
