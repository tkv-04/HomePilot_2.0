# Wake Word Customization Guide

## Default Wake Word

HomePilot uses **"Jarvis"** as the default wake word via Picovoice Porcupine. This works on both Linux and Windows.

## Changing to a Built-in Keyword

Porcupine includes several built-in keywords:

```yaml
wakeword:
  keyword: "alexa"  # or: computer, hey google, jarvis, ok google, picovoice, etc.
```

Available keywords vary by platform. Check [Porcupine docs](https://picovoice.ai/docs/porcupine/) for the full list.

## Training a Custom Wake Word

### Using Picovoice Console

1. Go to [console.picovoice.ai](https://console.picovoice.ai)
2. Select **Porcupine** → **Custom Wake Word**
3. Enter your desired wake word
4. Select target platform:
   - **Raspberry Pi:** Linux ARM
   - **Windows:** Windows x86_64
5. Download the `.ppn` file

### Using the Custom Keyword

Place the `.ppn` file in your `models/` directory and update config:

```yaml
wakeword:
  custom_keyword_path: "models/my_wake_word.ppn"
  sensitivity: 0.6
```

> **Important:** Porcupine `.ppn` files are platform-specific. If you run on both Linux and Windows, you need separate `.ppn` files for each platform and can switch via the config file.

## Adjusting Sensitivity

```yaml
wakeword:
  sensitivity: 0.6  # Range: 0.0 - 1.0
```

| Value | Behavior |
|-------|----------|
| 0.0 | Fewest false activations, may miss detections |
| 0.5 | Balanced (recommended starting point) |
| 0.7 | More responsive, slightly more false activations |
| 1.0 | Maximum responsiveness |

**Tip:** Start at 0.5. Increase by 0.1 if it misses detections. Decrease if it triggers randomly.

## Tips for Custom Wake Words

- **2-3 syllables** work best (e.g., "Hey Pilot", "Okay Home")
- Avoid words that sound like common speech
- Test in your actual environment with ambient noise
- The Picovoice free tier allows custom training
