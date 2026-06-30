"""Voice language service — enumerate and describe installed TTS voices.

Provides safe discovery of available system voices with language metadata,
used to populate the voice language/voice name dropdowns in settings.
"""

from __future__ import annotations

import logging

log = logging.getLogger("hard_workers.voice.language_service")

# Mapping from language codes found in pyttsx3 voice metadata
# to human-readable names.
_LANGUAGE_MAP: dict[str, str] = {
    "ara": "Arabic",
    "ar": "Arabic",
    "ar_SA": "Arabic (Saudi Arabia)",
    "eng": "English",
    "en": "English",
    "en_US": "English (US)",
    "en_GB": "English (UK)",
    "fra": "French",
    "fre": "French",
    "fr": "French",
    "fr_FR": "French (France)",
    "de": "German",
    "de_DE": "German (Germany)",
    "spa": "Spanish",
    "es": "Spanish",
    "es_ES": "Spanish (Spain)",
    "ita": "Italian",
    "it": "Italian",
    "ja": "Japanese",
    "jpn": "Japanese",
    "ko": "Korean",
    "kor": "Korean",
    "zh": "Chinese",
    "chi": "Chinese",
    "zho": "Chinese",
    "ru": "Russian",
    "rus": "Russian",
    "pt": "Portuguese",
    "por": "Portuguese",
    "nl": "Dutch",
    "nld": "Dutch",
    "pl": "Polish",
    "pol": "Polish",
    "sv": "Swedish",
    "swe": "Swedish",
}

# Language codes we explicitly support in the UI
_STT_LANGUAGES = {
    "auto": "Auto-detect",
    "en": "English",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ru": "Russian",
}


def _voice_language(voice: dict) -> str:
    """Extract a human-readable language name from a voice dict."""
    langs: list[str] = voice.get("lang", [])
    for lang in langs:
        if isinstance(lang, bytes):
            lang = lang.decode("utf-8", errors="replace")
        lang = lang.strip()
        # Try exact match first
        if lang in _LANGUAGE_MAP:
            return _LANGUAGE_MAP[lang]
        # Try prefix match (e.g. "en_US" from "en_US.utf-8")
        for prefix, name in _LANGUAGE_MAP.items():
            if lang.startswith(prefix):
                return name
    # Try to guess from voice name
    name = (voice.get("name") or "").lower()
    if "arab" in name or "saudi" in name:
        return "Arabic"
    if "english" in name or "american" in name or "british" in name:
        return "English"
    return "Unknown"


def get_stt_language_options() -> dict[str, str]:
    """Return STT language options as ``{value: label}`` dict."""
    return dict(_STT_LANGUAGES)


def enumerate_voices(tts) -> list[dict]:
    """Return sorted list of installed TTS voices with language metadata.

    Each entry::

        {
            "id": "com.apple.speech.synthesis.voice...",
            "name": "Samantha",
            "language": "English",
            "language_code": "en_US",
        }

    Returns empty list if TTS is unavailable.
    """
    if not tts or not hasattr(tts, "get_voices"):
        return []
    try:
        raw = tts.get_voices()
    except Exception:
        log.debug("Failed to enumerate TTS voices")
        return []

    result = []
    for v in raw:
        lang_display = _voice_language(v)
        lang_codes: list[str] = v.get("lang", [])
        primary_code = ""
        for lc in lang_codes:
            if isinstance(lc, bytes):
                lc = lc.decode("utf-8", errors="replace")
            if lc and not primary_code:
                primary_code = lc
            break
        result.append({
            "id": v.get("id", ""),
            "name": v.get("name", "Unknown"),
            "language": lang_display,
            "language_code": primary_code,
        })

    result.sort(key=lambda x: (x["language"], x["name"]))
    return result


def get_voice_languages(voices: list[dict]) -> list[str]:
    """Return unique, sorted language names from a voice list."""
    seen: set[str] = set()
    langs: list[str] = []
    for v in voices:
        lang = v.get("language", "Unknown")
        if lang not in seen:
            seen.add(lang)
            langs.append(lang)
    langs.sort()
    return langs


def get_voices_by_language(voices: list[dict], language: str) -> list[dict]:
    """Filter voices list to a specific language."""
    if not language:
        return list(voices)
    return [v for v in voices if v.get("language", "") == language]


def find_voice_by_id(voices: list[dict], voice_id: str) -> dict | None:
    """Find a voice dict by its ID."""
    for v in voices:
        if v.get("id") == voice_id:
            return v
    return None


def find_voice_by_name(voices: list[dict], name: str) -> dict | None:
    """Find a voice dict by its name."""
    for v in voices:
        if v.get("name") == name:
            return v
    return None


def detect_system_default(tts) -> str | None:
    """Return the voice ID of the system default TTS voice, if any."""
    if not tts or not hasattr(tts, "get_voices"):
        return None
    try:
        raw = tts.get_voices()
        if raw:
            return raw[0].get("id")
    except Exception as exc:
        log.warning("Failed to detect default voice: %s", exc)
    return None


def detect_arabic_voice(tts) -> str | None:
    """Return the first Arabic voice ID, or None."""
    if not tts or not hasattr(tts, "get_voices"):
        return None
    try:
        for v in tts.get_voices():
            lang = _voice_language(v)
            if lang == "Arabic":
                return v.get("id")
    except Exception as exc:
        log.warning("Failed to detect Arabic voice: %s", exc)
    return None
