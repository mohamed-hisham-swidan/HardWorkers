"""Per-message audio playback manager with pygame.mixer.

Architecture
————
AudioManager (singleton)
  └── registry: dict[msg_id, MessageAudioController]
       └── each controller owns its own pygame.mixer.Sound + Channel

Concurrency rules:
  - All pygame.mixer calls on the UI thread.
  - edge-tts synthesis runs on a daemon thread pool.
  - Per-controller generation counter prevents stale synthesis results.
  - Controllers are fully independent; stopping one does not affect others.

States per controller:
  IDLE → LOADING → PLAYING ↔ PAUSED
                    ↓          ↓
                  ERROR      IDLE (on natural end or stop)

UI sync via on_state_change callback (runs on UI thread).
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

from backend.voice.tts_engine import TTSEngine

if TYPE_CHECKING:
    import pygame

log = logging.getLogger("hard_workers.voice.audio_manager")

# ── Ensure mixer is initialised exactly once ────────────────────────
_mixer_inited = False
_mixer_lock = threading.Lock()


def _ensure_mixer(num_channels: int = 32) -> None:
    global _mixer_inited
    if _mixer_inited:
        return
    with _mixer_lock:
        if _mixer_inited:
            return
        try:
            import pygame

            pygame.mixer.pre_init(frequency=24000, size=-16, channels=1)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(num_channels)
            _mixer_inited = True
            log.info("pygame.mixer initialised (24kHz, mono, %d channels)", num_channels)
        except Exception as exc:
            log.warning("pygame.mixer init failed: %s", exc)


# ── States ───────────────────────────────────────────────────────────


class AudioState(Enum):
    IDLE = auto()
    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()
    ERROR = auto()


# ── Per-message controller ──────────────────────────────────────────


class MessageAudioController:
    """Independent audio controller for a single message."""

    def __init__(self, msg_id: str, on_state_change: Callable[[AudioState], None] | None = None) -> None:
        self._msg_id = msg_id
        self._on_state_change = on_state_change
        self._state = AudioState.IDLE

        self._sound: pygame.mixer.Sound | None = None
        self._channel: pygame.mixer.Channel | None = None
        self._tmp_path: str | None = None

        # Generation counter for stale-synthesis protection
        self._gen = 0
        self._lock = threading.Lock()

        # Voice override (None = use default)
        self._voice: str | None = None

    # ── Public API ──────────────────────────────────────────────────

    @property
    def state(self) -> AudioState:
        return self._state

    def play(self, text: str) -> None:
        """Start (or restart) playback for this message."""
        if not text or not TTSEngine.is_available():
            return

        self._stop_internal()

        gen = self._bump_gen()
        self._set_state(AudioState.LOADING)

        def _synthesise():
            if self._is_gen_stale(gen):
                return
            try:
                mp3_bytes = TTSEngine.synthesize(text, self._voice or "en-US-JennyNeural")
            except Exception as exc:
                log.warning("Synthesis failed for msg %s: %s", self._msg_id, exc)
                self._schedule_ui(lambda: self._on_synthesis_error(gen))
                return
            self._schedule_ui(lambda: self._on_synthesis_done(gen, mp3_bytes))

        threading.Thread(target=_synthesise, daemon=True).start()

    def pause(self) -> None:
        if self._state == AudioState.PLAYING and self._channel:
            self._channel.pause()
            self._set_state(AudioState.PAUSED)

    def resume(self) -> None:
        if self._state == AudioState.PAUSED and self._channel:
            self._channel.unpause()
            self._set_state(AudioState.PLAYING)
            self._start_completion_watch()

    def stop(self) -> None:
        self._stop_internal()
        self._set_state(AudioState.IDLE)

    def set_voice(self, voice: str) -> None:
        self._voice = voice

    def close(self) -> None:
        self._stop_internal()
        self._on_state_change = None

    # ── Internal helpers ────────────────────────────────────────────

    def _stop_internal(self) -> None:
        self._bump_gen()
        if self._channel:
            try:
                self._channel.stop()
            except Exception:
                log.debug("Channel stop failed (already released)")
            self._channel = None
        self._sound = None
        self._cleanup_tmp()

    def _bump_gen(self) -> int:
        with self._lock:
            self._gen += 1
            return self._gen

    def _is_gen_stale(self, gen: int) -> bool:
        with self._lock:
            return gen != self._gen

    def _set_state(self, state: AudioState) -> None:
        self._state = state
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception as exc:
                log.debug("State change callback failed: %s", exc)

    def _schedule_ui(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the UI thread via the manager's page reference."""
        page = AudioManager._page_ref
        if page is not None:
            try:
                page.run_thread(fn)
                return
            except Exception:
                log.debug("Page run_thread failed, calling fn directly")
        try:
            fn()
        except Exception as exc:
            log.warning("UI callback failed in _schedule_ui: %s", exc)

    def _on_synthesis_done(self, gen: int, mp3_bytes: bytes) -> None:
        if self._is_gen_stale(gen):
            return
        if self._state != AudioState.LOADING:
            return

        try:
            import pygame

            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(mp3_bytes)
            tmp.close()
            self._tmp_path = tmp.name

            self._sound = pygame.mixer.Sound(self._tmp_path)
            self._channel = self._sound.play()
            self._set_state(AudioState.PLAYING)
            self._start_completion_watch()
        except Exception as exc:
            log.warning("Playback start failed for msg %s: %s", self._msg_id, exc)
            self._on_synthesis_error(gen)

    def _on_synthesis_error(self, gen: int) -> None:
        if self._is_gen_stale(gen):
            return
        self._set_state(AudioState.ERROR)

    def _start_completion_watch(self) -> None:
        gen = self._bump_gen()

        def _watch():
            while not self._is_gen_stale(gen):
                if self._channel is None or not self._channel.get_busy():
                    self._schedule_ui(lambda: self._on_playback_ended(gen))
                    return
                time.sleep(0.1)

        threading.Thread(target=_watch, daemon=True).start()

    def _on_playback_ended(self, gen: int) -> None:
        if self._is_gen_stale(gen):
            return
        # Reset to IDLE only if we're still in a playing-like state
        if self._state in (AudioState.PLAYING, AudioState.LOADING):
            self._sound = None
            self._channel = None
            self._cleanup_tmp()
            self._set_state(AudioState.IDLE)

    def _cleanup_tmp(self) -> None:
        if self._tmp_path:
            try:
                os.unlink(self._tmp_path)
            except Exception:
                log.debug("Temp file cleanup skipped (already removed)")
            self._tmp_path = None


# ── Manager ──────────────────────────────────────────────────────────


class AudioManager:
    """Singleton registry of per-message audio controllers."""

    _instance: AudioManager | None = None
    _init_lock = threading.Lock()
    _page_ref = None

    @classmethod
    def init(cls, page=None, num_channels: int = 32) -> AudioManager:
        with cls._init_lock:
            if cls._instance is None:
                _ensure_mixer(num_channels)
                cls._instance = cls()
            if page is not None:
                cls._page_ref = page
        return cls._instance

    @classmethod
    def get_instance(cls) -> AudioManager:
        if cls._instance is None:
            raise RuntimeError("AudioManager not initialised. Call AudioManager.init() first.")
        return cls._instance

    def __init__(self) -> None:
        self._controllers: dict[str, MessageAudioController] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self, msg_id: str, on_state_change: Callable[[AudioState], None] | None = None
    ) -> MessageAudioController:
        with self._lock:
            if msg_id not in self._controllers:
                self._controllers[msg_id] = MessageAudioController(msg_id, on_state_change)
            ctrl = self._controllers[msg_id]
            if on_state_change and ctrl._on_state_change is None:
                ctrl._on_state_change = on_state_change
            return ctrl

    def release(self, msg_id: str) -> None:
        with self._lock:
            ctrl = self._controllers.pop(msg_id, None)
        if ctrl:
            ctrl.close()

    def stop_all(self) -> None:
        with self._lock:
            for ctrl in self._controllers.values():
                ctrl.stop()

    def release_all(self) -> None:
        with self._lock:
            for ctrl in self._controllers.values():
                ctrl.close()
            self._controllers.clear()
