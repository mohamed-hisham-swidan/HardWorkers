"""Speech-to-Text with multi-language support (Arabic, English, auto-detect).

Supports:
- Google Speech Recognition (online, 100+ languages)
- Arabic speech-to-text (ar-SA)
- Auto language detection via multi-pass recognition
- Microphone device selection
- Immediate stop via threading.Event
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger("hard_workers.voice.stt")

try:
    import speech_recognition as sr
except ImportError:
    sr = None  # type: ignore[assignment]

_SUPPORTED_LANGUAGES = {
    "en": "en-US",
    "ar": "ar-SA",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "zh": "zh-CN",
    "ja": "ja-JP",
    "ru": "ru-RU",
}


class SpeechToText:
    """Converts microphone audio to text with multi-language support.

    Falls back gracefully when no speech recognition library is available.
    Supports auto-detection of input language and microphone device selection.
    """

    def __init__(self, device_index: int | None = None) -> None:
        self._listening = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._recognizer = None
        self._microphone = None
        self._available = False
        self._device_index = device_index
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            self._recognizer = sr.Recognizer() if sr else None
            self._microphone = sr.Microphone(device_index=self._device_index) if sr else None
            self._available = True
            dev = f"device={self._device_index}" if self._device_index is not None else "default device"
            log.info("Speech-to-text initialized (speech_recognition + pyaudio, %s)", dev)
        except ImportError:
            log.warning(
                "STT not available — install pyaudio and speech_recognition: pip install pyaudio SpeechRecognition"
            )
        except OSError as exc:
            log.warning("STT microphone init failed (invalid device?): %s", exc)
        except Exception as exc:
            log.warning("STT init failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_available(self) -> bool:
        return self._available

    def start_listening(
        self,
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
        language: str = "auto",
    ) -> None:
        """Start listening on a background thread.

        Args:
            on_result: Called with transcribed text.
            on_error: Called with error message.
            language: ISO language code (e.g. 'en', 'ar') or 'auto' for auto-detect.
        """
        if not self._available:
            on_error("Speech recognition not available (install speech_recognition)")
            return
        if self._listening:
            return
        self._stop_event.clear()
        self._listening = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(on_result, on_error, language),
            daemon=True,
        )
        self._thread.start()

    def stop_listening(self) -> None:
        """Signal the listen loop to stop and wait for the thread to finish."""
        log.info("STT stop_listening called")
        self._listening = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                log.warning("STT listen thread did not finish within timeout")
            self._thread = None

    def _listen_loop(
        self,
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
        language: str,
    ) -> None:
        with self._microphone as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            while self._listening and not self._stop_event.is_set():
                try:
                    audio = self._recognizer.listen(
                        source,
                        timeout=0.3,
                        phrase_time_limit=15,
                    )
                    if not (self._listening and not self._stop_event.is_set()):
                        return
                    text = self._recognize(audio, language)
                    if text and text.strip():
                        on_result(text.strip())
                        return
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as exc:
                    log.warning("STT API error: %s", exc)
                    on_error(f"Speech recognition error: {exc}")
                    return
                except Exception:
                    log.exception("STT error")
                    on_error("Speech recognition failed")
                    return

    def _recognize(self, audio, language: str) -> str | None:
        """Recognize speech with optional auto language detection."""
        try:
            if language == "auto":
                return self._auto_detect(audio)
            lang_code = _SUPPORTED_LANGUAGES.get(language, language)
            return self._recognizer.recognize_google(audio, language=lang_code)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            raise

    def _auto_detect(self, audio) -> str | None:
        """Try multiple languages and return the first confident result."""
        priorities = ["ar-SA", "en-US", "fr-FR", "es-ES", "de-DE"]
        for lang in priorities:
            try:
                result = self._recognizer.recognize_google(audio, language=lang)
                if result and result.strip():
                    log.info("Auto-detected language: %s", lang)
                    return result.strip()
            except (sr.UnknownValueError, sr.RequestError):
                continue
        return None

    def close(self) -> None:
        self.stop_listening()
