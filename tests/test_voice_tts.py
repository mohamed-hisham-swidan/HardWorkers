"""Comprehensive tests for the redesigned TextToSpeech system.

Tests cover:
  - Single speech
  - Multiple speeches
  - Stop()
  - Stop + speak
  - Rapid clicks
  - Concurrent operations
  - Race conditions
  - Application shutdown
  - Long messages
  - Cached voices
  - on_done callback
  - Stress tests
  - Randomized scenarios
"""

from __future__ import annotations

import logging
import random
import threading
import time

import pytest

from backend.voice.tts import TextToSpeech

# Disable debug logging during tests for cleaner output
logging.getLogger("hard_workers.voice.tts").setLevel(logging.WARNING)

_SHORT_TEXT = "Hello."
_LONG_TEXT = ". ".join(["This is a moderately long sentence"] * 3)  # ~100 chars, ~5s speech
_VERY_LONG_TEXT = ". ".join(["This is a very long sentence"] * 3)  # ~75 chars, ~4s speech
_TIMEOUT = 30  # max seconds to wait for speech to complete
_POLL = 0.05  # polling interval


def _wait_until(tts: TextToSpeech, target: bool, timeout: float = _TIMEOUT) -> bool:
    """Poll ``is_speaking`` until it reaches ``target``."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if tts.is_speaking == target:
            return True
        time.sleep(_POLL)
    return False


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def tts() -> TextToSpeech:
    engine = TextToSpeech()
    if not engine.available:
        pytest.skip("TTS engine not available on this system")
    yield engine
    engine.close()


# ═══════════════════════════════════════════════════════════════════
# 1. Basic lifecycle
# ═══════════════════════════════════════════════════════════════════


class TestLifecycle:
    def test_available_property(self, tts: TextToSpeech) -> None:
        assert tts.available is True

    def test_is_speaking_starts_false(self, tts: TextToSpeech) -> None:
        assert tts.is_speaking is False

    def test_single_speech_completes(self, tts: TextToSpeech) -> None:
        tts.speak(_SHORT_TEXT)
        assert tts.is_speaking is True
        assert _wait_until(tts, False) is True
        assert tts.is_speaking is False

    def test_voices_property(self, tts: TextToSpeech) -> None:
        voices = tts.voices
        assert isinstance(voices, list)
        if voices:
            assert "id" in voices[0]
            assert "name" in voices[0]
            assert "lang" in voices[0]

    def test_get_voices_backward_compat(self, tts: TextToSpeech) -> None:
        assert tts.get_voices() == tts.voices


# ═══════════════════════════════════════════════════════════════════
# 2. Multiple speeches
# ═══════════════════════════════════════════════════════════════════


class TestMultipleSpeeches:
    def test_two_sequential(self, tts: TextToSpeech) -> None:
        tts.speak("First.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False

        tts.speak("Second.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False

    def test_rapid_enqueue(self, tts: TextToSpeech) -> None:
        """Queue 5 short utterances — all should be spoken in sequence."""
        for i in range(5):
            tts.speak(f"Message {i}.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_still_works_after_rapid_enqueue(self, tts: TextToSpeech) -> None:
        for _ in range(5):
            tts.speak("Spam.")
        assert _wait_until(tts, False)
        tts.speak("After spam.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 3. Stop behavior
# ═══════════════════════════════════════════════════════════════════


class TestStop:
    def test_stop_while_idle(self, tts: TextToSpeech) -> None:
        tts.stop()
        assert tts.is_speaking is False

    def test_stop_sets_is_speaking_false(self, tts: TextToSpeech) -> None:
        tts.speak(_SHORT_TEXT)
        assert tts.is_speaking is True
        tts.stop()
        assert tts.is_speaking is False

    def test_stop_drains_queue(self, tts: TextToSpeech) -> None:
        tts.speak("First.")
        tts.speak("Second.")
        tts.speak("Third.")
        tts.stop()
        # Queue drained, worker has nothing to do
        # (the first utterance may still be playing, but no more)
        time.sleep(0.5)
        # A fresh speak should work
        tts.speak("After drain.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_stop_then_speak(self, tts: TextToSpeech) -> None:
        tts.speak("First.")
        time.sleep(0.2)
        tts.stop()
        assert tts.is_speaking is False
        tts.speak("Second.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False

    def test_stop_does_not_fire_on_done(self, tts: TextToSpeech) -> None:
        """stop() prevents the on_done callback from firing."""
        fired = []

        def callback() -> None:
            fired.append(True)

        tts.on_done = callback
        tts.speak(_SHORT_TEXT)
        time.sleep(0.1)
        tts.stop()
        # Wait for speech to physically finish (worker still plays current)
        time.sleep(3)
        assert len(fired) == 0
        tts.on_done = None


# ═══════════════════════════════════════════════════════════════════
# 4. Stop + speak patterns
# ═══════════════════════════════════════════════════════════════════


class TestStopSpeakPatterns:
    def test_five_stop_speak_cycles(self, tts: TextToSpeech) -> None:
        for i in range(5):
            tts.speak(f"Cycle {i}.")
            time.sleep(0.1)
            tts.stop()
            assert tts.is_speaking is False
        # Confirm still works
        tts.speak("Final.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False

    def test_rapid_stop_speak_no_wait(self, tts: TextToSpeech) -> None:
        """Alternate stop/speak without waiting between them."""
        for _ in range(10):
            tts.speak("X.")
            tts.stop()
        assert tts.is_speaking is False
        tts.speak("Y.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 5. Rapid clicks (simulates UI spam)
# ═══════════════════════════════════════════════════════════════════


class TestRapidClicks:
    def test_rapid_speak_calls(self, tts: TextToSpeech) -> None:
        for _ in range(20):
            tts.speak("Click.")
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_rapid_speak_interleaved_sleep(self, tts: TextToSpeech) -> None:
        for i in range(10):
            tts.speak(f"Click {i}.")
            time.sleep(random.uniform(0.01, 0.05))
        assert _wait_until(tts, False)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 6. Concurrent operations (multi-threaded)
# ═══════════════════════════════════════════════════════════════════


class TestConcurrentOperations:
    def test_concurrent_stop_speak_no_barrier(self, tts: TextToSpeech) -> None:
        """Race stop() from a thread against speak() from main thread."""
        for _ in range(20):
            t1 = threading.Thread(target=tts.stop, daemon=True)
            t1.start()
            tts.speak("Race.")
            t1.join()
        # After all races, verify is_speaking eventually becomes False
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_parallel_speak_calls(self, tts: TextToSpeech) -> None:
        """Call speak() from multiple threads simultaneously."""
        threads = []
        for i in range(10):
            t = threading.Thread(target=lambda i=i: tts.speak(f"Thread {i}."), daemon=True)
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_concurrent_stop_from_multiple_threads(self, tts: TextToSpeech) -> None:
        """Call stop() from many threads at once — no crash."""
        tts.speak("Message to speak while testing.")
        time.sleep(0.3)
        threads = [threading.Thread(target=tts.stop, daemon=True) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert tts.is_speaking is False
        tts.speak("After concurrent stops.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=10)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 7. Race conditions
# ═══════════════════════════════════════════════════════════════════


class TestRaceConditions:
    def test_speak_during_run_and_wait(self, tts: TextToSpeech) -> None:
        """Speak while worker is busy — subsequent items should queue."""
        tts.speak("First long message that takes time to pronounce.")
        tts.speak("Second message queued during first.")
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_stop_while_queue_has_items(self, tts: TextToSpeech) -> None:
        """Stop should drain all queued items."""
        tts.speak("First.")
        tts.speak("Second.")
        tts.speak("Third.")
        tts.stop()
        time.sleep(0.5)
        # Only the first may have started, but the rest were drained
        tts.speak("Fourth.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=5)
        assert tts.is_speaking is False

    def test_is_speaking_not_stuck_true(self, tts: TextToSpeech) -> None:
        """After any sequence of operations, is_speaking must settle to False."""
        for _ in range(20):
            tts.speak("Test.")
            time.sleep(random.uniform(0.01, 0.1))
            if random.random() < 0.3:
                tts.stop()
        assert _wait_until(tts, False)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 8. Application shutdown
# ═══════════════════════════════════════════════════════════════════


class TestShutdown:
    def test_close_while_idle(self) -> None:
        tts = TextToSpeech()
        if not tts.available:
            pytest.skip("TTS not available")
        t0 = time.monotonic()
        tts.close()
        elapsed = time.monotonic() - t0
        assert elapsed < 6, f"close() took {elapsed:.2f}s"

    def test_close_during_speech(self) -> None:
        tts = TextToSpeech()
        if not tts.available:
            pytest.skip("TTS not available")
        tts.speak(_LONG_TEXT)
        time.sleep(0.3)
        t0 = time.monotonic()
        tts.close()
        elapsed = time.monotonic() - t0
        assert elapsed < 6, f"close() took {elapsed:.2f}s"

    def test_close_is_idempotent(self, tts: TextToSpeech) -> None:
        tts.close()
        tts.close()  # second call should not crash

    def test_speak_after_close_is_noop(self, tts: TextToSpeech) -> None:
        tts.close()
        tts.speak("After close.")  # must not crash
        assert tts.is_speaking is False
        assert tts.available is False

    def test_stop_after_close_is_noop(self, tts: TextToSpeech) -> None:
        tts.close()
        tts.stop()  # must not crash
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 9. Long messages
# ═══════════════════════════════════════════════════════════════════


class TestLongMessages:
    def test_long_text(self, tts: TextToSpeech) -> None:
        tts.speak(_LONG_TEXT)
        assert tts.is_speaking is True
        assert _wait_until(tts, False)
        assert tts.is_speaking is False

    def test_very_long_text_with_stop(self, tts: TextToSpeech) -> None:
        tts.speak(_VERY_LONG_TEXT)
        time.sleep(0.5)
        tts.stop()
        assert tts.is_speaking is False
        tts.speak("After long stop.")
        assert tts.is_speaking is True
        assert _wait_until(tts, False, timeout=10)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 10. on_done callback
# ═══════════════════════════════════════════════════════════════════


class TestOnDoneCallback:
    def test_callback_fires_on_natural_completion(self, tts: TextToSpeech) -> None:
        fired = threading.Event()

        def callback() -> None:
            fired.set()

        tts.on_done = callback
        tts.speak(_SHORT_TEXT)
        assert fired.wait(timeout=_TIMEOUT) is True
        assert tts.is_speaking is False
        tts.on_done = None

    def test_callback_not_fired_on_stop(self, tts: TextToSpeech) -> None:
        fired = []

        def callback() -> None:
            fired.append(True)

        tts.on_done = callback
        tts.speak(_SHORT_TEXT)
        time.sleep(0.1)
        tts.stop()
        time.sleep(2)
        assert len(fired) == 0
        tts.on_done = None

    def test_callback_swappable(self, tts: TextToSpeech) -> None:
        results = []

        def cb1() -> None:
            results.append("cb1")

        def cb2() -> None:
            results.append("cb2")

        tts.on_done = cb1
        tts.speak("First.")
        assert _wait_until(tts, False, timeout=5)
        # at this point cb1 should have fired
        tts.on_done = cb2
        tts.speak("Second.")
        assert _wait_until(tts, False, timeout=5)
        assert results == ["cb1", "cb2"]
        tts.on_done = None

    def test_callback_none_sets_no_callback(self, tts: TextToSpeech) -> None:
        tts.on_done = None
        tts.speak(_SHORT_TEXT)
        assert _wait_until(tts, False)

    def test_callback_exception_does_not_crash(self, tts: TextToSpeech) -> None:
        def callback() -> None:
            raise RuntimeError("boom")

        tts.on_done = callback
        tts.speak(_SHORT_TEXT)
        assert _wait_until(tts, False)
        tts.on_done = None


# ═══════════════════════════════════════════════════════════════════
# 11. Settings (set_voice, set_speed)
# ═══════════════════════════════════════════════════════════════════


class TestSettings:
    def test_set_speed(self, tts: TextToSpeech) -> None:
        tts.set_speed(250)
        tts.speak(_SHORT_TEXT)
        assert _wait_until(tts, False)

    def test_set_voice(self, tts: TextToSpeech) -> None:
        voices = tts.voices
        if not voices:
            pytest.skip("No voices available")
        tts.set_voice(voices[0]["id"])
        tts.speak(_SHORT_TEXT)
        assert _wait_until(tts, False)

    def test_speed_does_not_break_is_speaking(self, tts: TextToSpeech) -> None:
        tts.set_speed(300)
        tts.speak(_SHORT_TEXT)
        assert tts.is_speaking is True
        assert _wait_until(tts, False)
        assert tts.is_speaking is False


# ═══════════════════════════════════════════════════════════════════
# 12. Stress tests
# ═══════════════════════════════════════════════════════════════════


class TestStress:
    def test_100_speak_cycles(self) -> None:
        for i in range(100):
            tts = TextToSpeech()
            if not tts.available:
                pytest.skip("TTS not available mid-test")
            for j in range(5):
                tts.speak(f"Cycle {i} message {j}.")
                time.sleep(random.uniform(0.01, 0.05))
            tts.stop()
            tts.speak(f"Cycle {i} final.")
            assert _wait_until(tts, False, timeout=5)
            tts.close()

    def test_50_randomized_scenarios(self) -> None:
        actions = ["speak", "stop", "speak", "speak", "stop", "speak"]
        for i in range(50):
            tts = TextToSpeech()
            if not tts.available:
                pytest.skip("TTS not available mid-test")
            for _ in range(random.randint(3, 8)):
                action = random.choice(actions)
                if action == "speak":
                    tts.speak(f"Random test {i}.")
                else:
                    tts.stop()
                time.sleep(random.uniform(0.01, 0.1))
            assert _wait_until(tts, False)
            assert tts.is_speaking is False
            tts.close()

    def test_no_deadlock_after_many_operations(self, tts: TextToSpeech) -> None:
        for _ in range(50):
            tts.speak("A.")
            tts.speak("B.")
            tts.stop()
            tts.speak("C.")
        assert _wait_until(tts, False)
        assert tts.is_speaking is False
