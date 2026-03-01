# Home Assistant Integration Guide

## Overview

HomePilot integrates with Home Assistant via the REST API. It supports:
- Controlling lights, switches, fans, locks
- Querying sensor values
- Running scenes and automations
- Local API (preferred) with Nabu Casa cloud fallback

## Setup

### 1. Create a Long-Lived Access Token

1. Open Home Assistant web UI
2. Go to your **Profile** (bottom-left)
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**
5. Name it "HomePilot"
6. Copy the token

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

Instead of putting the token in plaintext config, store it encrypted:

```python
from homepilot.security.token_store import TokenStore

store = TokenStore("data/.keyfile")
store.store_token("ha_token", "YOUR_LONG_LIVED_TOKEN")
```

Then set `use_encrypted_token: true` in config and leave `access_token` empty.

## Voice Commands

### Device Control
- "Turn on the kitchen light"
- "Turn off the bedroom fan"
- "Set the living room light to 50 percent"

### Sensors
- "What's the temperature?"
- "What's the humidity reading?"

### Scenes & Automations
- "Activate movie night scene"
- "Run the goodnight automation"

## Nabu Casa Cloud Fallback

If you have a [Nabu Casa](https://www.nabucasa.com/) subscription:

```yaml
home_assistant:
  cloud_url: "https://your-instance.ui.nabu.casa"
  prefer_local: true   # Still tries local first
```

HomePilot will automatically fall back to the cloud URL if the local API is unreachable.

## Entity Naming Tips

HomePilot searches for entities by matching your voice command against entity IDs and friendly names. For best results:

- Use clear, descriptive **friendly names** in HA
  - ✅ "Kitchen Light" — matches "turn on the kitchen light"
  - ❌ "light.switch_relay_7c_03" — harder to match
- Keep names unique per room
- Voice commands support partial matching

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Not connected to HA" | Verify `local_url` is reachable: `curl http://IP:8123/api/ -H "Authorization: Bearer TOKEN"` |
| "Entity not found" | Check entity naming in HA. Use `Developer Tools > States` to see exact entity IDs. |
| Cloud fallback not working | Verify Nabu Casa subscription is active and `cloud_url` is correct. |
| Timeout errors | Increase `timeout` value. Check network connectivity. |
