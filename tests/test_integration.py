"""Quick integration test for all HomePilot subsystems."""
import traceback

results = []

def test(name, fn):
    try:
        fn()
        results.append(("PASS", name))
        print(f"[PASS] {name}")
    except Exception as e:
        results.append(("FAIL", name))
        print(f"[FAIL] {name}: {e}")


from homepilot.config.settings import Settings
s = Settings.load()
test("Config + .env loading", lambda: None)

# Security
from homepilot.security.validator import SecurityValidator
test("Security validator", lambda: SecurityValidator(s.security))

# Intent parser
from homepilot.intent_engine.intent_parser import IntentParser
def test_intent():
    ip = IntentParser(confidence_threshold=0.5)
    r = ip.parse("set a timer for 5 minutes")
    assert r.name, "No intent detected"
    print(f"       Intent={r.name} slots={r.slots}")
test("Intent parser", test_intent)

# Entity resolver
from homepilot.entity_resolver.resolver import EntityResolver
def test_entity():
    er = EntityResolver()
    e = er.resolve("set_timer", {"duration": "5 minutes"})
    print(f"       Entities={e}")
test("Entity resolver", test_entity)

# Audio stream
from homepilot.audio_input.audio_stream import AudioStream
test("Audio stream", lambda: AudioStream(s.audio))

# Wake word
from homepilot.wakeword.detector import WakeWordDetector
def test_wakeword():
    wd = WakeWordDetector(s.wakeword)
    wd.initialize()
    print(f"       frame_length={wd.frame_length}")
    wd.cleanup()
test("Wake word detector", test_wakeword)

# STT
from homepilot.speech_to_text.stt_engine import STTEngine
def test_stt():
    stt = STTEngine(s.stt, s.audio)
    stt.initialize()
    stt.cleanup()
test("STT engine (Vosk)", test_stt)

# TTS
from homepilot.tts.tts_engine import TTSEngine
def test_tts():
    tts = TTSEngine(s.tts)
    tts.initialize()
    tts.speak_blocking("Test complete.")
    tts.shutdown()
test("TTS engine", test_tts)

# OS control
from homepilot.os_control.system_commands import SystemController
def test_os():
    sc = SystemController(s.os_control)
    print(f"       Platform={sc.get_platform()}")
test("OS control", test_os)

# Personality
from homepilot.utils.personality import Personality
def test_personality():
    p = Personality("Jarvis")
    print(f"       {p.greeting()}")
test("Personality", test_personality)

# Context memory
from homepilot.utils.context_memory import ContextMemory
test("Context memory", lambda: ContextMemory())

# Timer manager
from homepilot.timers.timer_manager import TimerManager
test("Timer manager", lambda: TimerManager(
    persistence_file="data/timers.json", max_concurrent=20
))

# Summary
print()
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {len(results)}")
if failed:
    for s, n in results:
        if s == "FAIL":
            print(f"  FAILED: {n}")
