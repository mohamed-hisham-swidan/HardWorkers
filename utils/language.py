"""Language detection and multilingual message wrapping.

Some models fine-tuned primarily on English data (e.g. NVIDIA Nemotron)
may refuse to respond in non-English scripts.  This module detects
user messages in non-Latin scripts and wraps them with explicit
language instructions placed immediately before the user's text,
where they have maximal influence on the model's output.
"""

from __future__ import annotations

import re

# ASCII + Latin-1 Supplement + Latin Extended-A/B cover all Western
# European languages.  Any codepoint above U+024F is a non-Latin
# script (Arabic, Hebrew, CJK, Cyrillic, Devanagari, Thai, etc.)
_NON_LATIN_RE = re.compile(r"[^\x00-\u024F]")


def contains_non_latin(text: str) -> bool:
    """Return True when *text* contains characters outside the Latin
    script range (U+0000–U+024F)."""
    return bool(_NON_LATIN_RE.search(text))


def wrap_for_multilingual(user_message: str) -> str:
    """Prepend an explicit language-instruction block to *user_message*
    when it contains non-Latin characters.

    The instruction is placed right in front of the user's original
    text so the model sees it at decode time, which is more effective
    than relying solely on a system prompt (which safety fine-tuning
    can override).
    """
    if not contains_non_latin(user_message):
        return user_message

    return (
        "LANGUAGE INSTRUCTION (you MUST follow this):\n"
        "The text below is written in a language other than English. "
        "You MUST respond in the same language. "
        "You are fully capable of understanding and replying in Arabic, "
        "Persian, Urdu, Hebrew, Turkish, Chinese, Japanese, Korean, "
        "Russian, Hindi, and all other languages. "
        "Never say you cannot understand or reply in the user's language.\n\n"
        f"---\n{user_message}\n---"
    )
