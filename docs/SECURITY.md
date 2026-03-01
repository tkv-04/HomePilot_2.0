# Security Hardening Guide

HomePilot is designed with security-first principles. This guide covers the security architecture and hardening recommendations.

## Security Architecture Overview

```
┌──────────────────────────────────────────┐
│              User Voice Input            │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│   Intent Parser      │ ← No shell access
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Security Validator   │ ← Whitelist + Rate Limit
│  ┌─────────────────┐ │
│  │ Input Sanitizer  │ │ ← Injection prevention
│  │ Rate Limiter     │ │ ← 30 cmd/min default
│  │ Whitelist Check  │ │ ← Strict command allow-list
│  └─────────────────┘ │
└──────────┬───────────┘
           │ ✓ PASS
           ▼
┌──────────────────────┐
│  Command Executor     │ ← Sandboxed subprocess
└──────────────────────┘
```

## Built-in Protections

### 1. Command Whitelisting
No arbitrary shell execution. Every command must be in the whitelist:
```yaml
os_control:
  allowed_apps: ["firefox", "vlc", "nautilus"]
  allowed_commands: ["shutdown", "reboot", "volume_up"]
```

### 2. Input Sanitization
All inputs are checked for injection patterns. Blocked characters: `; & | \` $ ( ) { } < > \\`

### 3. Rate Limiting
Default: 30 commands per minute per command type.
```yaml
security:
  enable_rate_limiting: true
  rate_limit_per_minute: 30
```

### 4. Encrypted Token Storage
API tokens are encrypted at rest using Fernet (AES-128-CBC):
```yaml
security:
  token_encryption_key_file: "data/.keyfile"
```
Key file permissions are set to `600` (owner-only read/write).

### 5. Sandboxed Execution
Subprocesses run with a minimal environment — only safe variables (PATH, HOME, LANG, DISPLAY) are passed.

### 6. Plugin Integrity Checking
Plugins are verified against a SHA256 manifest before loading:
```yaml
security:
  enable_plugin_integrity: true
plugins:
  manifest_file: "plugins/manifest.json"
```

Generate a manifest after adding/updating plugins:
```python
from homepilot.plugins.plugin_manager import PluginManager
pm = PluginManager(plugin_dir="plugins")
pm.generate_manifest()
```

### 7. systemd Security
The service file includes:
- `NoNewPrivileges=true` — prevents privilege escalation
- `ProtectSystem=strict` — read-only filesystem
- `ProtectHome=read-only` — limited home directory access
- `PrivateTmp=true` — isolated temp directory
- `MemoryMax=512M` / `CPUQuota=80%` — resource limits

## Hardening Recommendations

### Network
- Enable `local_only_mode` to block all outbound network requests
- Use firewall rules to restrict traffic:
  ```bash
  sudo ufw default deny incoming
  sudo ufw default deny outgoing
  sudo ufw allow out to 192.168.0.0/16  # Local network only
  ```

### Filesystem
- Set restrictive permissions on the data directory:
  ```bash
  chmod 700 data/
  chmod 600 data/.keyfile data/.tokens.enc
  ```

### Confirmation for Dangerous Commands
```yaml
os_control:
  require_confirmation: ["shutdown", "reboot"]
```

### Disable Unused Features
```yaml
home_assistant:
  enabled: false  # If not using HA
os_control:
  enabled: false  # If not needing OS commands
plugins:
  enabled: false  # If not using plugins
```

### Log Security
Secure logging automatically redacts tokens, access keys, passwords, and Bearer tokens from all log output.
