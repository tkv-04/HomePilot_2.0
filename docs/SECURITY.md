# Security Hardening Guide

HomePilot is designed with security-first principles. This guide covers the security architecture and hardening recommendations for both Linux and Windows.

## Security Architecture

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
  allowed_apps:
    - "firefox"    # Cross-platform
    - "vlc"
    - "explorer"   # Windows
    - "nautilus"   # Linux
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

### 5. Sandboxed Execution (Platform-Aware)
Subprocesses run with a minimal environment:
- **Linux:** Only `PATH`, `HOME`, `USER`, `LANG`, `DISPLAY`, X11/Wayland vars
- **Windows:** Only `PATH`, `SYSTEMROOT`, `TEMP`, `USERPROFILE`, `COMSPEC`, `WINDIR`

### 6. Plugin Integrity Checking
Plugins are verified against a SHA256 manifest before loading:
```python
from homepilot.plugins.plugin_manager import PluginManager
pm = PluginManager(plugin_dir="plugins")
pm.generate_manifest()
```

### 7. systemd Security (Linux)
The service file includes:
- `NoNewPrivileges=true` — prevents privilege escalation
- `ProtectSystem=strict` — read-only filesystem
- `ProtectHome=read-only` — limited home access
- `PrivateTmp=true` — isolated temp directory
- `MemoryMax=512M` / `CPUQuota=80%` — resource limits

## Platform-Specific Hardening

### Linux

```bash
# Firewall — local network only
sudo ufw default deny incoming
sudo ufw default deny outgoing
sudo ufw allow out to 192.168.0.0/16

# File permissions
chmod 700 data/
chmod 600 data/.keyfile data/.tokens.enc
```

### Windows

```powershell
# Restrict data folder access (PowerShell as Admin)
$acl = Get-Acl "data"
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $env:USERNAME, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($rule)
Set-Acl "data" $acl

# Windows Firewall — block outbound for HomePilot
New-NetFirewallRule -DisplayName "HomePilot Block Outbound" `
    -Direction Outbound -Program "venv\Scripts\python.exe" -Action Block
```

## General Recommendations

- Enable `local_only_mode: true` to block all outbound network requests
- Require confirmation for dangerous commands:
  ```yaml
  os_control:
    require_confirmation: ["shutdown", "reboot"]
  ```
- Disable unused features:
  ```yaml
  home_assistant:
    enabled: false
  plugins:
    enabled: false
  ```
- Secure logging automatically redacts tokens, access keys, passwords, and Bearer tokens from all log output
