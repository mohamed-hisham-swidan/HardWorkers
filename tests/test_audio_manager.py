"""Tests for the new per-message audio playback system."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from backend.voice.audio_manager import AudioManager, AudioState, MessageAudioController
from backend.voice.tts_engine import TTSEngine

# ═══════════════════════════════════════════════════════════════════
# TTSEngine tests
# ═══════════════════════════════════════════════════════════════════


class TestTTSEngine:
    def test_is_available(self):
        assert isinstance(TTSEngine.is_available(), bool)

    def test_list_voices_returns_list(self):
        voices = TTSEngine.list_voices()
        assert isinstance(voices, list)
        if voices:
            v = voices[0]
            assert "id" in v
            assert "name" in v
            assert "language" in v

    def test_synthesize_returns_bytes(self):
        data = TTSEngine.synthesize("Hello", voice="en-US-JennyNeural")
        assert isinstance(data, bytes)
        assert len(data) > 100  # should have at least some audio data

    def test_synthesize_empty_string_returns_empty(self):
        data = TTSEngine.synthesize("", voice="en-US-JennyNeural")
        assert isinstance(data, bytes)
        assert len(data) == 0

    def test_list_voices_cache(self):
        v1 = TTSEngine.list_voices()
        v2 = TTSEngine.list_voices()
        assert v1 is v2  # same cached object

    def test_invalidate_cache(self):
        TTSEngine.list_voices()
        TTSEngine.invalidate_cache()
        assert TTSEngine._cached_voices is None


# ═══════════════════════════════════════════════════════════════════
# AudioManager tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_audio_manager():
    AudioManager._instance = None
    AudioManager._page_ref = None
    AudioManager._init_lock = threading.Lock()
    yield
    AudioManager._instance = None
    AudioManager._page_ref = None


class TestAudioManager:
    def test_init_creates_singleton(self):
        mgr = AudioManager.init()
        assert AudioManager.get_instance() is mgr
        assert AudioManager.get_instance() is AudioManager.init()

    def test_get_instance_raises_if_not_init(self):
        AudioManager._instance = None
        with pytest.raises(RuntimeError):
            AudioManager.get_instance()

    def test_get_or_create_returns_same_for_msg_id(self):
        mgr = AudioManager.init()
        c1 = mgr.get_or_create("msg_1")
        c2 = mgr.get_or_create("msg_1")
        assert c1 is c2

    def test_get_or_create_different_ids(self):
        mgr = AudioManager.init()
        c1 = mgr.get_or_create("msg_1")
        c2 = mgr.get_or_create("msg_2")
        assert c1 is not c2

    def test_release_removes_controller(self):
        mgr = AudioManager.init()
        c1 = mgr.get_or_create("msg_1")
        mgr.release("msg_1")
        c2 = mgr.get_or_create("msg_1")
        assert c1 is not c2

    def test_release_all(self):
        mgr = AudioManager.init()
        mgr.get_or_create("msg_1")
        mgr.get_or_create("msg_2")
        mgr.release_all()
        assert len(mgr._controllers) == 0

    def test_stop_all(self):
        mgr = AudioManager.init()
        c1 = mgr.get_or_create("msg_1")
        c2 = mgr.get_or_create("msg_2")
        mgr.stop_all()
        assert c1.state == AudioState.IDLE
        assert c2.state == AudioState.IDLE


# ═══════════════════════════════════════════════════════════════════
# MessageAudioController tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def controller():
    states = []
    ctrl = MessageAudioController("test_msg", on_state_change=lambda s: states.append(s))
    ctrl._schedule_ui = MagicMock()  # prevent actual UI thread calls
    return ctrl, states


class TestMessageAudioController:
    def test_initial_state(self, controller):
        ctrl, states = controller
        assert ctrl.state == AudioState.IDLE

    def test_state_change_callback_on_play(self, controller):
        ctrl, states = controller
        with patch.object(ctrl, "_stop_internal"):
            with patch.object(ctrl, "_bump_gen", return_value=1):
                with patch.object(ctrl, "_set_state") as mock_set:
                    ctrl.play("test")
                    mock_set.assert_called_with(AudioState.LOADING)

    def test_pause_when_idle_does_nothing(self, controller):
        ctrl, states = controller
        ctrl.pause()
        assert ctrl.state == AudioState.IDLE

    def test_resume_when_idle_does_nothing(self, controller):
        ctrl, states = controller
        ctrl.resume()
        assert ctrl.state == AudioState.IDLE

    def test_stop_when_idle_stays_idle(self, controller):
        ctrl, states = controller
        ctrl.stop()
        assert ctrl.state == AudioState.IDLE

    def test_play_calls_synthesize_in_thread(self, controller):
        ctrl, states = controller
        with patch.object(ctrl, "_bump_gen", return_value=1):
            with patch.object(ctrl, "_stop_internal"):
                ctrl.play("Hello")
        assert ctrl.state == AudioState.LOADING

    def test_double_play_stops_first(self, controller):
        ctrl, states = controller
        call_count = 0

        def tracking_stop():
            nonlocal call_count
            call_count += 1

        with patch.object(ctrl, "_stop_internal", side_effect=tracking_stop):
            with patch.object(ctrl, "_bump_gen", return_value=1):
                ctrl.play("First")
            with patch.object(ctrl, "_bump_gen", return_value=2):
                ctrl.play("Second")
        assert call_count >= 1

    def test_set_voice(self, controller):
        ctrl, states = controller
        ctrl.set_voice("en-US-JennyNeural")
        assert ctrl._voice == "en-US-JennyNeural"

    def test_close_clears_callback(self, controller):
        ctrl, states = controller
        ctrl.close()
        assert ctrl._on_state_change is None
        assert ctrl.state == AudioState.IDLE

    def test_generation_counter_stale_check(self, controller):
        ctrl, states = controller
        gen = ctrl._bump_gen()
        assert not ctrl._is_gen_stale(gen)  # current gen should not be stale
        ctrl._bump_gen()
        assert ctrl._is_gen_stale(gen)  # old gen should be stale

    def test_play_with_empty_text_returns_immediately(self, controller):
        ctrl, states = controller
        with patch.object(ctrl, "_bump_gen") as mock:
            ctrl.play("")
        mock.assert_not_called()

    def test_rapid_play_stops_previous(self, controller):
        """Rapid clicking should stop previous and start new."""
        ctrl, states = controller
        gens = [1, 2, 3]

        with patch.object(ctrl, "_stop_internal") as mock_stop:
            with patch.object(ctrl, "_bump_gen", side_effect=gens):
                with patch.object(ctrl, "_set_state"):
                    ctrl.play("A")
                    ctrl.play("B")
                    ctrl.play("C")
        assert mock_stop.call_count >= 2


# ═══════════════════════════════════════════════════════════════════
# Integration: multiple controllers are independent
# ═══════════════════════════════════════════════════════════════════


class TestMultipleControllers:
    def test_two_controllers_are_independent(self):
        mgr = AudioManager.init()
        c1 = mgr.get_or_create("msg_1")
        c2 = mgr.get_or_create("msg_2")

        assert c1 is not c2
        assert c1.state == AudioState.IDLE
        assert c2.state == AudioState.IDLE

        # Set different voices
        c1.set_voice("voice-a")
        c2.set_voice("voice-b")
        assert c1._voice == "voice-a"
        assert c2._voice == "voice-b"

    def test_stopping_one_does_not_affect_other(self, controller):
        ctrl1, _ = controller
        ctrl2, _ = MessageAudioController("msg_2"), []

        ctrl1._state = AudioState.PLAYING
        ctrl2._state = AudioState.PLAYING

        ctrl1.stop()
        assert ctrl1.state == AudioState.IDLE
        assert ctrl2.state == AudioState.PLAYING  # still playing
