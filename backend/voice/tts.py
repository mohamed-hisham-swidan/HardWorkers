"""Text-to-Speech using system TTS (pyttsx3).

Architecture
————
Single dedicated worker thread owns the pyttsx3 engine for its entire
lifetime.  The public API enqueues commands; the worker processes them
sequentially.  This eliminates all cross-thread COM corruption
("run loop already started").

A generation counter (``_gen``) enables cancellation without touching
the engine: ``stop()`` bumps the counter and drains the queue; the
worker checks ``gen == _gen`` before speaking and after completion, so
cancelled utterances are silently skipped and ``is_speaking`` stays
consistent.

Voices are cached at init time so ``get_voices()`` never touches the
engine from the caller's thread.

A single ``on_done`` callback fires from the worker thread when an
utterance completes naturally (gen still matches).  No polling required.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

log = logging.getLogger("hard_workers.voice.tts")


class TextToSpeech:
    """Thread-safe TTS with single-worker-engine architecture.

    Public API is callable from any thread.
    Engine is only touched by the dedicated worker thread.
    """

    _SENTINEL = object()

    def __init__(self) -> None:
        self._engine = None
        self._available = False
        self._voice_id: str = ""
        self._rate: int = 180

        # Generation counter (protect with _lock)
        self._is_speaking = False
        self._gen = 0
        self._lock = threading.Lock()

        # Command queue + cached voices
        self._queue: queue.Queue = queue.Queue()
        self._cached_voices: list[dict] = []
        self._engine_ready = threading.Event()
        self._shutdown = threading.Event()

        # Completion callback (set by controller)
        self._on_done: Callable[[], None] | None = None

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

        if not self._engine_ready.wait(timeout=10):
            log.warning("TTS engine did not become ready within 10s")

    # ── Worker loop ─────────────────────────────────────────────────

    def _run(self) -> None:
        engine = None
        try:
            import pyttsx3

            engine = pyttsx3.init()
            log.info("TTS initialized on worker thread")
            self._cached_voices = self._enumerate_voices(engine)
        except ImportError:
            log.warning("pyttsx3 not installed — TTS unavailable")
        except Exception as exc:
            log.warning("TTS init failed on worker: %s", exc)
        finally:
            self._engine = engine
            self._available = engine is not None
            self._engine_ready.set()

        if not engine:
            return

        try:
            while not self._shutdown.is_set():
                try:
                    item = self._queue.get(timeout=0.3)
                except queue.Empty:
                    continue

                if item is self._SENTINEL:
                    break

                cmd = item[0]

                if cmd == "speak":
                    self._process_speak(engine, item[1], item[2])
                elif cmd == "get_voices":
                    self._queue.put(self._cached_voices)
        finally:
            try:
                engine.stop()
            except Exception:
                log.debug("Engine stop during TTS cleanup ignored")

    def _process_speak(self, engine, text: str, gen: int) -> None:
        with self._lock:
            if gen != self._gen:
                return

        self._is_speaking = True

        try:
            if self._voice_id:
                try:
                    engine.setProperty("voice", self._voice_id)
                except Exception as exc:
                    log.warning("Failed to set voice: %s", exc)
            try:
                engine.setProperty("rate", self._rate)
            except Exception as exc:
                log.warning("Failed to set rate: %s", exc)

            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            log.warning("TTS playback error: %s", exc)
        finally:
            with self._lock:
                still_current = gen == self._gen
                if still_current:
                    self._is_speaking = False
            if still_current:
                self._fire_done()

    def _enumerate_voices(self, engine) -> list[dict]:
        try:
            return [{"id": v.id, "name": v.name, "lang": v.languages} for v in engine.getProperty("voices")]
        except Exception:
            log.debug("Failed to enumerate TTS voices")
            return []

    def _fire_done(self) -> None:
        cb = self._on_done
        if cb:
            try:
                cb()
            except Exception:
                log.debug("TTS on_done callback failed")

    # ── Public API ──────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def voices(self) -> list[dict]:
        """Cached voice list — safe to call from any thread."""
        return self._cached_voices

    @property
    def on_done(self) -> Callable[[], None] | None:
        return self._on_done

    @on_done.setter
    def on_done(self, cb: Callable[[], None] | None) -> None:
        self._on_done = cb

    def speak(self, text: str) -> None:
        """Enqueue text for speech.  Returns immediately."""
        if not self._available or not text.strip():
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._is_speaking = True
        self._queue.put(("speak", text, gen))

    def stop(self) -> None:
        """Cancel all pending speech.

        The current utterance (if any) continues playing — the engine
        is never touched from this thread.  The generation counter
        ensures the worker skips the result and does not fire on_done.
        """
        with self._lock:
            self._is_speaking = False
            self._gen += 1
        try:
            while True:
                item = self._queue.get_nowait()
                if item is self._SENTINEL:
                    self._queue.put(self._SENTINEL)
                    break
        except queue.Empty:
            pass

    def get_voices(self) -> list[dict]:
        """Same as ``.voices`` — kept for backward compatibility."""
        return self._cached_voices

    def set_voice(self, voice_id: str) -> None:
        """Set voice ID (applied lazily by worker)."""
        self._voice_id = voice_id

    def set_speed(self, rate: int = 180) -> None:
        """Set speech rate (applied lazily by worker)."""
        self._rate = rate

    def close(self) -> None:
        """Shut down the worker thread and release the engine."""
        self.stop()
        self._shutdown.set()
        # Force-interrupt engine if stuck in a long runAndWait().
        # Cross-thread COM is acceptable here — the engine is being
        # destroyed and this is a one-time shutdown operation.
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                log.debug("Engine stop during shutdown ignored")
        self._queue.put(self._SENTINEL)
        self._worker.join(timeout=5)
        if self._worker.is_alive():
            log.warning("TTS worker did not shut down cleanly")
        self._available = False
        self._engine = None
