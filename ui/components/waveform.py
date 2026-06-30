"""Animated waveform visualization for voice recording."""

from __future__ import annotations

import logging
import random
import threading
import time

import flet as ft

from ui.helpers import Colors

log = logging.getLogger("hard_workers.ui.waveform")


class WaveformAnimation(ft.Container):
    """Pulsing waveform bars that animate during voice recording."""

    def __init__(self, bar_count: int = 5) -> None:
        self._bar_count = bar_count
        self._running = False
        self._thread: threading.Thread | None = None
        self._bars: list[ft.Container] = []

        bar_container = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        for _ in range(bar_count):
            bar = ft.Container(
                width=4,
                height=12,
                bgcolor=Colors.ERROR,
                border_radius=2,
                animate=ft.Animation(150, "ease_in_out"),
            )
            self._bars.append(bar)
            bar_container.controls.append(bar)

        super().__init__(
            content=bar_container,
            visible=False,
            padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        )

    def start(self) -> None:
        self._running = True
        self.visible = True
        try:
            self.update()
        except Exception:
            log.debug("Waveform start update failed")
        self._thread = threading.Thread(target=self._animate_loop, daemon=True)
        self._thread.start()

    def retheme(self) -> None:
        """Re-apply current Colors palette to waveform bars."""
        for bar in self._bars:
            bar.bgcolor = Colors.ERROR
        try:
            self.update()
        except Exception:
            pass

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        self.visible = False
        try:
            self.update()
        except Exception:
            log.debug("Waveform stop update failed")

    def _animate_loop(self) -> None:
        while self._running:
            for bar in self._bars:
                h = random.randint(8, 28)
                bar.height = h
                bar.bgcolor = (
                    Colors.ERROR if h > 18 else Colors.WARNING if h > 12 else Colors.with_opacity(Colors.ERROR, 0.5)
                )
            try:
                page = self.page
                if page is not None:
                    page.run_thread(lambda: self.update())
                else:
                    self.update()
            except Exception:
                log.debug("Waveform animation update failed")
            time.sleep(0.12)


class RecordingIndicator(ft.Container):
    """Visual indicator showing recording state with pulsing dot."""

    def __init__(self) -> None:
        self._dot = ft.Container(
            width=10,
            height=10,
            bgcolor=Colors.ERROR,
            border_radius=5,
            animate=ft.Animation(500, "ease_in_out"),
        )
        self._label = ft.Text(
            "Recording\u2026",
            size=12,
            color=Colors.ERROR,
            weight=ft.FontWeight.BOLD,
        )
        self._processing_label = ft.Text(
            "Processing\u2026",
            size=12,
            color=Colors.WARNING,
            weight=ft.FontWeight.BOLD,
            visible=False,
        )

        super().__init__(
            content=ft.Row(
                [self._dot, self._label, self._processing_label],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
            padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        )

    def retheme(self) -> None:
        """Re-apply current Colors palette to recording indicator."""
        self._dot.bgcolor = Colors.ERROR
        self._label.color = Colors.ERROR
        self._processing_label.color = Colors.WARNING
        try:
            self.update()
        except Exception:
            pass

    def show_recording(self) -> None:
        self.visible = True
        self._label.visible = True
        self._processing_label.visible = False
        try:
            self.update()
        except Exception:
            log.debug("Recording indicator show_recording failed")

    def show_processing(self) -> None:
        self._label.visible = False
        self._processing_label.visible = True
        try:
            self.update()
        except Exception:
            log.debug("Recording indicator show_processing failed")

    def hide(self) -> None:
        self.visible = False
        try:
            self.update()
        except Exception:
            log.debug("Recording indicator hide failed")
