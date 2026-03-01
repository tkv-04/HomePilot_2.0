# Wake Word Customization Guide

## Default Wake Word

HomePilot uses **"Jarvis"** as the default wake word via Picovoice Porcupine.

## Changing to a Built-in Keyword

Porcupine includes several built-in keywords. To change:

```yaml
wakeword:
  keyword: "alexa"  # or: computer, hey google, jarvis, ok google, picovoice, etc.
```

Available built-in keywords vary by platform. Check [Porcupine docs](https://picovoice.ai/docs/porcupine/) for the full list.

## Training a Custom Wake Word

### Using Picovoice Console

1. Go to [console.picovoice.ai](https://console.picovoice.ai)
2. Select **Porcupine** → **Custom Wake Word**
3. Enter your desired wake word
4. Select target platform: **Raspberry Pi (Linux ARM)**
5. Download the `.ppn` file

### Using the Custom Keyword

1. Place the `.ppn` file in your `models/` directory:
   ```
   models/my_wake_word_en_raspberry-pi.ppn
   ```

2. Update config:
   ```yaml
   wakeword:
     custom_keyword_path: "models/my_wake_word_en_raspberry-pi.ppn"
     sensitivity: 0.6
   ```

## Adjusting Sensitivity

```yaml
wakeword:
  sensitivity: 0.6  # Range: 0.0 - 1.0
```

| Value | Behavior |
|-------|----------|
| 0.0 | Fewest false activations, may miss some detections |
| 0.5 | Balanced (recommended starting point) |
| 0.7 | More responsive, slightly more false activations |
| 1.0 | Maximum responsiveness, most false activations |

**Tip**: Start at 0.5 and increase by 0.1 if the wake word is being missed. Decrease if it's triggering randomly.

## Multiple Wake Words (Future)

The architecture supports multiple wake words. To add support:

1. Train additional `.ppn` files
2. Modify `WakeWordDetector` to accept a list of keyword paths
3. Pass multiple sensitivities (one per keyword)

## Tips for Custom Wake Words

- **2-3 syllables** work best (e.g., "Hey Pilot", "Okay Home")
- Avoid words that sound like common speech
- Test in your actual environment with ambient noise
- The Picovoice free tier allows custom training
