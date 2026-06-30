"""Minimal mic/STT controller — separate from audio playback."""

from __future__ import annotations

import logging

import flet as ft

from ui.helpers import Colors

log = logging.getLogger("ui.controllers.mic")


class MicController:
    """Manages STT recording only. Audio playback is handled by AudioManager."""

    def __init__(
        self,
        page,
        stt,
        btn_mic,
        waveform,
        rec_indicator,
        entry,
        *,
        on_update_input_bar_visibility=None,
        on_show_toast=None,
    ):
        self._page = page
        self._stt = stt
        self._btn_mic = btn_mic
        self._waveform = waveform
        self._rec_indicator = rec_indicator
        self._entry = entry
        self._on_update_input_bar_visibility = on_update_input_bar_visibility
        self._on_show_toast = on_show_toast
        self._is_recording = False
        self._rec_version = 0

    @property
    def available(self) -> bool:
        return self._stt is not None and self._stt.is_available

    def toggle_mic(self, _e=None) -> None:
        if not self.available:
            if self._on_show_toast:
                self._on_show_toast("Speech recognition unavailable", Colors.ERROR)
            return

        if self._is_recording:
            log.info("MIC_STOP_REQUESTED rec_version=%d", self._rec_version)
            self._stt.stop_listening()
            self._is_recording = False
            self._update_mic_ui_idle()
            self._invoke_input_bar("idle")
        else:
            self._rec_version += 1
            version = self._rec_version
            log.info("MIC_START_REQUESTED rec_version=%d", version)
            self._is_recording = True
            self._invoke_input_bar("recording")
            self._update_mic_ui_recording()

            def on_result(text: str, _v: int = version) -> None:
                if _v != self._rec_version:
                    log.info("MIC_STALE_RESULT rec_version=%d expected=%d", _v, self._rec_version)
                    return
                self._is_recording = False
                self._page.run_thread(
                    lambda: (
                        self._rec_indicator.show_processing(),
                        self._waveform.stop(),
                        self._update_mic_ui_idle(),
                        self._rec_indicator.hide(),
                        self._on_voice_result(text),
                    )
                )

            def on_error(msg: str, _v: int = version) -> None:
                if _v != self._rec_version:
                    log.info("MIC_STALE_ERROR rec_version=%d expected=%d", _v, self._rec_version)
                    return
                self._is_recording = False
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
            log.debug("Mic UI idle update ignored: %s", exc)

    def _update_mic_ui_recording(self) -> None:
        self._btn_mic.icon = ft.Icons.STOP_ROUNDED
        self._btn_mic.icon_color = Colors.TEXT_HIGH
        self._btn_mic.bgcolor = Colors.ERROR
        self._waveform.start()
        self._rec_indicator.show_recording()
        try:
            self._btn_mic.update()
        except Exception as exc:
            log.debug("Mic UI recording update ignored: %s", exc)

    def _invoke_input_bar(self, mode: str) -> None:
        if self._on_update_input_bar_visibility:
            self._on_update_input_bar_visibility(mode)

    def close(self) -> None:
        if self._is_recording and self._stt:
            try:
                self._stt.stop_listening()
            except Exception:
                log.debug("STT stop on close ignored")
        if self._stt:
            try:
                self._stt.close()
            except Exception:
                log.debug("STT close ignored")
