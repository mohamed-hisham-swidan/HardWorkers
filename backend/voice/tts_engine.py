"""Modern TTS engine using edge-tts (Microsoft Edge online voices).

Synchronous wrapper around edge-tts's async API.
Safe to call from any thread, including threads with a running asyncio loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from typing import ClassVar

log = logging.getLogger("hard_workers.voice.tts_engine")

_DEFAULT_VOICE = "en-US-JennyNeural"

_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts-async")


def _run_async(coro_factory, timeout: float = 30):
    """Run an async coroutine from any sync context.

    If the current thread already has a running event loop (e.g. Flet's
    main thread), the coroutine is executed on a dedicated daemon thread.
    Otherwise it runs inline via ``asyncio.run()``.
    """
    try:
        asyncio.get_running_loop()
        # Already inside an event loop — use a thread
        fut = _THREAD_POOL.submit(lambda: asyncio.run(coro_factory()))
        return fut.result(timeout=timeout)
    except RuntimeError:
        # No running loop — run inline
        return asyncio.run(coro_factory())


class TTSEngine:
    """Stateless TTS engine. Each synthesize call is independent."""

    _available: ClassVar[bool | None] = None
    _cached_voices: ClassVar[list[dict]] | None = None
    _avail_lock = threading.Lock()

    @classmethod
    def is_available(cls) -> bool:
        if cls._available is None:
            with cls._avail_lock:
                if cls._available is None:
                    cls._check_available()
        return cls._available

    @classmethod
    def _check_available(cls) -> None:
        try:
            import edge_tts

            _run_async(lambda: edge_tts.list_voices(), timeout=10)
            cls._available = True
        except Exception as exc:
            log.debug("edge-tts unavailable: %s", exc)
            cls._available = False

    @classmethod
    def synthesize(cls, text: str, voice: str = _DEFAULT_VOICE) -> bytes:
        """Synthesize text to MP3 bytes. Blocks calling thread."""
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            return bytes(data)

        try:
            return _run_async(_run, timeout=60)
        except Exception as exc:
            log.warning("TTS synthesis failed: %s", exc)
            raise

    @classmethod
    def list_voices(cls) -> list[dict]:
        """Return list of available voices in settings-compatible format."""
        if cls._cached_voices is not None:
            return cls._cached_voices

        import edge_tts

        async def _run():
            raw = await edge_tts.list_voices()
            result = []
            for v in raw:
                locale = v.get("Locale", "")
                language = _locale_to_display(locale)
                result.append({
                    "id": v["Name"],
                    "name": v["FriendlyName"] or v["ShortName"],
                    "language": language,
                    "language_code": locale,
                    "gender": v.get("Gender", ""),
                })
            result.sort(key=lambda x: (x["language"], x["name"]))
            return result

        try:
            cls._cached_voices = _run_async(_run, timeout=30)
        except Exception as exc:
            log.warning("Failed to list edge-tts voices: %s", exc)
            cls._cached_voices = []
        return cls._cached_voices

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._cached_voices = None


def _locale_to_display(locale: str) -> str:
    """Convert a locale string (e.g. en-US) to a human-readable language name."""
    lang_map = {
        "af": "Afrikaans",
        "am": "Amharic",
        "ar": "Arabic",
        "az": "Azerbaijani",
        "bg": "Bulgarian",
        "bn": "Bengali",
        "bs": "Bosnian",
        "ca": "Catalan",
        "cs": "Czech",
        "cy": "Welsh",
        "da": "Danish",
        "de": "German",
        "el": "Greek",
        "en": "English",
        "es": "Spanish",
        "et": "Estonian",
        "eu": "Basque",
        "fa": "Persian",
        "fi": "Finnish",
        "fil": "Filipino",
        "fr": "French",
        "ga": "Irish",
        "gl": "Galician",
        "gu": "Gujarati",
        "he": "Hebrew",
        "hi": "Hindi",
        "hr": "Croatian",
        "hu": "Hungarian",
        "hy": "Armenian",
        "id": "Indonesian",
        "is": "Icelandic",
        "it": "Italian",
        "ja": "Japanese",
        "jv": "Javanese",
        "ka": "Georgian",
        "kk": "Kazakh",
        "km": "Khmer",
        "kn": "Kannada",
        "ko": "Korean",
        "lo": "Lao",
        "lt": "Lithuanian",
        "lv": "Latvian",
        "mk": "Macedonian",
        "ml": "Malayalam",
        "mn": "Mongolian",
        "mr": "Marathi",
        "ms": "Malay",
        "mt": "Maltese",
        "my": "Burmese",
        "ne": "Nepali",
        "nl": "Dutch",
        "no": "Norwegian",
        "pa": "Punjabi",
        "pl": "Polish",
        "ps": "Pashto",
        "pt": "Portuguese",
        "ro": "Romanian",
        "ru": "Russian",
        "si": "Sinhala",
        "sk": "Slovak",
        "sl": "Slovenian",
        "so": "Somali",
        "sq": "Albanian",
        "sr": "Serbian",
        "su": "Sundanese",
        "sv": "Swedish",
        "sw": "Swahili",
        "ta": "Tamil",
        "te": "Telugu",
        "th": "Thai",
        "tr": "Turkish",
        "uk": "Ukrainian",
        "ur": "Urdu",
        "uz": "Uzbek",
        "vi": "Vietnamese",
        "zh": "Chinese",
        "zu": "Zulu",
    }
    base = locale.split("-")[0] if locale else ""
    return lang_map.get(base, base or "Unknown")
