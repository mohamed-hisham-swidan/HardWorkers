"""Clipboard service for safe text copying."""

from __future__ import annotations

import logging
import sys
import traceback

log = logging.getLogger("utils.clipboard")


def _ensure_sta() -> None:
    """Ensure COM is initialized as STA on Windows (required by Win32 clipboard API)."""
    if sys.platform == "win32":
        try:
            import ctypes
            import ctypes.wintypes

            ole32 = ctypes.windll.ole32
            # COINIT_APARTMENTTHREADED = 0x2
            ole32.CoInitializeEx(None, 0x2)
            log.debug("COM initialized as STA")
        except Exception as e:
            log.debug("COM init skipped (already initialized?): %s", e)


def copy_to_clipboard(text: str) -> bool:
    """Copies text to clipboard. Returns True on success, False on failure."""
    try:
        _ensure_sta()
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception as e:
        log.warning("Clipboard operation failed: %s %s", type(e).__name__, e)
        log.debug("Clipboard traceback:\n%s", traceback.format_exc())
        return False
