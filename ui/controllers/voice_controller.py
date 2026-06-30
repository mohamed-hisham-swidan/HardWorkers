"""Voice controller — mediates between UI and voice backend (STT/TTS).

State machine (TTS):
  IDLE → SPEAKING  (on speak_response / toggle_tts on)
  SPEAKING → IDLE  (on completion callback or stop)

No polling threads.  The TTS backend fires ``on_done`` from its worker
thread when speech completes naturally; the controller uses that to
restore state and notify the UI callback on the Flet thread via
``page.run_thread``.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto

import flet as ft

from ui.helpers import Colors

log = logging.getLogger("ui.controllers.voice")


class VoiceState(Enum):
    """Public-facing state exposed to UI layer."""

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class _ControllerState(Enum):
    """Internal state machine."""

    IDLE = auto()
    SPEAKING = auto()


class VoiceController:
    """Manages STT recording and TTS playback for chat voice features.

    Thread safety: ``_lock`` protects all mutable state.
    The TTS ``on_done`` callback replaces the old polling-thread pattern.
    """

    def __init__(
        self,
        page,
        stt,
        tts,
        btn_mic,
        btn_tts,
        waveform,
        rec_indicator,
        entry,
        *,
        on_update_input_bar_visibility=None,
        on_show_toast=None,
    ):
        self._page = page
        self._stt = stt
        self._tts = tts
        self._btn_mic = btn_mic
        self._btn_tts = btn_tts
        self._waveform = waveform
        self._rec_indicator = rec_indicator
        self._entry = entry
        self._on_update_input_bar_visibility = on_update_input_bar_visibility
        self._on_show_toast = on_show_toast

        # State machine
        self._lock = threading.Lock()
        self._state = _ControllerState.IDLE
        self._active_listen_cb = None
        self._speak_gen = 0  # guards against stale completion callbacks

        # STT state (simple toggle)
        self._voice_state = VoiceState.IDLE

        # Register TTS completion callback — fires from worker thread.
        if self._tts:
            self._tts.on_done = self._on_speech_completed

    # ── Properties ──────────────────────────────────────────────────

    @property
    def state(self) -> VoiceState:
        return self._voice_state

    @property
    def stt_available(self) -> bool:
        return self._stt is not None and self._stt.is_available

    @property
    def tts_available(self) -> bool:
        return self._tts is not None and self._tts.available

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._state == _ControllerState.SPEAKING

    # ── TTS completion callback ─────────────────────────────────────

    def _on_speech_completed(self) -> None:
        """Called from TTS worker thread when speech finishes naturally."""
        with self._lock:
            if self._state != _ControllerState.SPEAKING:
                return
            gen = self._speak_gen
            cb = self._active_listen_cb
            self._active_listen_cb = None
            self._state = _ControllerState.IDLE
        if cb:
            try:
                self._page.run_thread(lambda: self._on_completion_ui(cb, gen))
            except Exception:
                log.debug("TTS completion UI update failed")

    def _on_completion_ui(self, cb, gen: int) -> None:
        """Runs on UI thread; discards if a newer speak has started."""
        with self._lock:
            if gen != self._speak_gen:
                return
        cb(False)

    # ── Mic toggle (STT) ────────────────────────────────────────────

    def toggle_mic(self, _e=None) -> None:
        if not self._stt or not self._stt.is_available:
            if self._on_show_toast:
                self._on_show_toast("Speech recognition unavailable", Colors.ERROR)
            return

        if self._voice_state == VoiceState.RECORDING:
            self._stt.stop_listening()
            self._voice_state = VoiceState.IDLE
            self._update_mic_ui_idle()
            self._invoke_input_bar("idle")
        elif self._voice_state == VoiceState.IDLE:
            self._voice_state = VoiceState.RECORDING
            self._invoke_input_bar("recording")
            self._update_mic_ui_recording()

            def on_result(text: str) -> None:
                self._voice_state = VoiceState.IDLE
                self._page.run_thread(
                    lambda: (
                        self._rec_indicator.show_processing(),
                        self._waveform.stop(),
                        self._update_mic_ui_idle(),
                        self._rec_indicator.hide(),
                        self._on_voice_result(text),
                    )
                )

            def on_error(msg: str) -> None:
                self._voice_state = VoiceState.IDLE
                self._page.run_thread(
                    lambda: (
                        self._update_mic_ui_idle(),
                        self._waveform.stop(),
                        self._rec_indicator.hide(),
                        self._on_show_toast and self._on_show_toast(msg, Colors.ERROR),
                    )
                )

            self._stt.start_listening(on_result=on_result, on_error=on_error, language="auto")

    def _on_voice_result(self, text: str) -> None:
        current = (self._entry.value or "").strip()
        self._entry.value = (current + " " + text) if current else text
        try:
            self._entry.update()
        except Exception:
            log.debug("Entry update on voice result ignored")

    def _update_mic_ui_idle(self) -> None:
        self._btn_mic.icon = ft.Icons.MIC
        self._btn_mic.icon_color = Colors.TEXT_MUTED2
        self._btn_mic.bgcolor = None
        self._waveform.stop()
        self._rec_indicator.hide()
        try:
            self._btn_mic.update()
        except Exception as exc:
            log.debug("Voice mic UI idle update ignored: %s", exc)

    def _update_mic_ui_recording(self) -> None:
        self._btn_mic.icon = ft.Icons.STOP_ROUNDED
        self._btn_mic.icon_color = Colors.TEXT_HIGH
        self._btn_mic.bgcolor = Colors.ERROR
        self._waveform.start()
        self._rec_indicator.show_recording()
        try:
            self._btn_mic.update()
        except Exception as exc:
            log.debug("Voice mic UI recording update ignored: %s", exc)

    # ── TTS speak response ──────────────────────────────────────────

    def speak_response(self, text: str | None, result_cb=None) -> None:
        """Speak text via TTS.  If already speaking, toggles off or switches."""
        with self._lock:
            if not self._tts or not self._tts.available or not text:
                if result_cb:
                    result_cb(False)
                return

            if self._state == _ControllerState.SPEAKING:
                log.info("TTS_STOP requested")
                self._tts.stop()
                is_same = self._active_listen_cb is result_cb
                if self._active_listen_cb and not is_same:
                    self._active_listen_cb(False)
                self._active_listen_cb = None
                if is_same:
                    log.info("TTS_TOGGLE_OFF")
                    self._state = _ControllerState.IDLE
                    result_cb and result_cb(False)
                    return
                log.info("TTS_SWITCH_MESSAGE")

            self._speak_gen += 1
            self._state = _ControllerState.SPEAKING
            self._active_listen_cb = result_cb

        try:
            self._tts.speak(text)
            if result_cb:
                result_cb(True)
        except Exception as exc:
            log.warning("TTS speak error: %s", exc)
            with self._lock:
                self._active_listen_cb = None
                self._state = _ControllerState.IDLE
            if result_cb:
                result_cb(False)

    # ── TTS toggle button ───────────────────────────────────────────

    _GREETING = "Hello, I am ready to read responses aloud"

    def toggle_tts(self, _e=None) -> None:
        if not self._tts or not self._tts.available:
            if self._on_show_toast:
                self._on_show_toast("Text-to-speech not available (install pyttsx3)", Colors.ERROR)
            return

        with self._lock:
            if self._state == _ControllerState.SPEAKING:
                log.info("TTS_BTN_STOP")
                self._tts.stop()
                if self._active_listen_cb:
                    cb = self._active_listen_cb
                    self._active_listen_cb = None
                    cb(False)
                self._state = _ControllerState.IDLE
                self._btn_tts.icon_color = Colors.TEXT_MUTED2
            elif self._state == _ControllerState.IDLE:
                log.info("TTS_BTN_START")
                self._speak_gen += 1
                self._state = _ControllerState.SPEAKING
                self._btn_tts.icon_color = Colors.PRIMARY
                self._tts.speak(self._GREETING)

        try:
            self._btn_tts.update()
        except Exception:
            log.debug("TTS button update skipped")

    # ── Helpers ─────────────────────────────────────────────────────

    def _invoke_input_bar(self, mode: str) -> None:
        if self._on_update_input_bar_visibility:
            self._on_update_input_bar_visibility(mode)

    def set_stt_language(self, language: str) -> None:
        self._stt_language = language

    # ── Cleanup ─────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._state = _ControllerState.IDLE
            self._active_listen_cb = None
        if self._tts:
            self._tts.on_done = None
            try:
                self._tts.close()
            except Exception:
                log.debug("TTS close on cleanup ignored")
        if self._stt:
            try:
                self._stt.close()
            except Exception:
                log.debug("STT close on cleanup ignored")
