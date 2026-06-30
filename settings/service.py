"""Settings persistence service with event-driven change notification.

Handles:
  - Loading / saving ``UserSettings`` to a JSON file.
  - Emitting ``SettingsChangedEvent`` on every ``set_*()`` call.
  - Migrating window geometry from the legacy ``settings.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.events import EventBus, SettingsChangedEvent
from settings.models import UserSettings
from utils.crypto import decrypt_value, encrypt_value, get_master_key

log = logging.getLogger("settings.service")

_LEGACY_FILE = "settings.json"
_SETTINGS_FILE = "data/settings.json"


def _deep_from_dict(d: dict) -> UserSettings:
    """Hydrate a ``UserSettings`` tree from a flat-ish JSON dict.

    Sub-dataclasses are constructed per category so that unknown keys are
    silently dropped and missing keys fall through to their default value.
    """
    import dataclasses
    from typing import get_type_hints

    def _build(dc_cls: type, data: dict) -> Any:
        kw = {}
        # Resolve type hints to actual classes (handles __future__.annotations)
        hints = get_type_hints(dc_cls)
        for f in dataclasses.fields(dc_cls):
            f_type = hints.get(f.name, f.type)
            if f.name in data:
                val = data[f.name]
                if dataclasses.is_dataclass(f_type):
                    kw[f.name] = _build(f_type, val) if isinstance(val, dict) else f.default
                else:
                    kw[f.name] = val
            else:
                kw[f.name] = f.default
        return dc_cls(**kw)

    return _build(UserSettings, d)


def _deep_to_dict(obj: Any) -> dict:
    """Serialize a nested dataclass tree to a plain JSON-safe dict."""
    import dataclasses

    if dataclasses.is_dataclass(obj):
        return {f.name: _deep_to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    return obj


def _migrate_legacy(settings: UserSettings) -> UserSettings:
    """Import ``width`` / ``height`` from the legacy ``settings.json``."""
    try:
        data = json.loads(Path(_LEGACY_FILE).read_text(encoding="utf-8"))
        w = data.get("width")
        h = data.get("height")
        if w is not None:
            settings.appearance.window_width = int(w)
        if h is not None:
            settings.appearance.window_height = int(h)
        Path(_LEGACY_FILE).rename(_LEGACY_FILE + ".bak")
        log.info("Migrated window geometry from legacy %s", _LEGACY_FILE)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("Legacy migration skipped (%s)", exc)
    return settings


class SettingsService:
    """Load, save, and mutate user settings with event-bus notifications."""

    def __init__(self, bus: EventBus, path: str | Path = _SETTINGS_FILE) -> None:
        self._bus = bus
        self._path = Path(path)
        self._settings = UserSettings.defaults()
        self._loaded = False

    # ── load / save ──────────────────────────────────────────────────────────

    # ── Key helpers ─────────────────────────────────────────────────────────

    def _get_key_path(self) -> Path:
        return self._path.parent / self._settings.security.master_key_file

    def _encrypt_providers(self, data: dict) -> None:
        key_path = self._get_key_path()
        if not self._settings.security.encrypt_api_keys:
            return
        key = get_master_key(key_path)
        providers = data.get("providers", {})
        for name in providers:
            entry = providers[name]
            if isinstance(entry, dict) and entry.get("api_key"):
                entry["api_key"] = encrypt_value(entry["api_key"], key)

    def _decrypt_providers(self, data: dict) -> None:
        key_path = self._get_key_path()
        if not key_path.exists():
            return
        key = get_master_key(key_path)
        providers = data.get("providers", {})
        for name in providers:
            entry = providers[name]
            if isinstance(entry, dict) and entry.get("api_key"):
                entry["api_key"] = decrypt_value(entry["api_key"], key)

    # ── load / save ──────────────────────────────────────────────────────────

    def load(self) -> UserSettings:
        """Load settings from disk, falling back to defaults."""
        if self._loaded:
            return self._settings
        self._loaded = True
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._decrypt_providers(raw)
            self._settings = _deep_from_dict(raw)
            log.info("Settings loaded from %s", self._path)
        except FileNotFoundError:
            self._settings = UserSettings.defaults()
            self._settings = _migrate_legacy(self._settings)
            log.info("No settings file — using defaults")
        except Exception as exc:
            log.warning("Failed to load settings (%s) — using defaults", exc)
            self._settings = UserSettings.defaults()
        return self._settings

    def save(self) -> None:
        """Persist current settings to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = _deep_to_dict(self._settings)
            self._encrypt_providers(data)
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.debug("Settings saved to %s", self._path)
        except Exception as exc:
            log.error("Failed to save settings: %s", exc)

    # ── read ─────────────────────────────────────────────────────────────────

    @property
    def current(self) -> UserSettings:
        return self._settings

    def raw(self) -> dict:
        return _deep_to_dict(self._settings)

    # ── category-level setters (each emits SettingsChangedEvent) ──────────────

    def set_general(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.general, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="general"))
        self.save()

    def set_appearance(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.appearance, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="appearance"))
        self.save()

    def set_models(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.models, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="models"))
        self.save()

    def set_providers(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._settings.providers, k):
                setattr(self._settings.providers, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="providers"))
        self.save()

    def set_provider_entry(self, provider: str, **kwargs: Any) -> None:
        entry = getattr(self._settings.providers, provider, None)
        if entry is not None:
            for k, v in kwargs.items():
                setattr(entry, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="providers"))
        self.save()

    def set_memory(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.memory, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="memory"))
        self.save()

    def set_workspaces(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.workspaces, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="workspaces"))
        self.save()

    def set_performance(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.performance, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="performance"))
        self.save()

    def set_voice(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.voice, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="voice"))
        self.save()

    def set_security(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.security, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="security"))
        self.save()

    def set_diagnostics(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.diagnostics, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="diagnostics"))
        self.save()

    def set_advanced(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.advanced, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="advanced"))
        self.save()

    def set_developer(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self._settings.developer, k, v)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="developer"))
        self.save()

    # ── bulk / reset ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._settings = UserSettings.defaults()
        self._bus.emit(SettingsChangedEvent(sender="settings", section="*"))
        self.save()
        log.info("Settings reset to defaults")

    def export_to_dict(self) -> dict:
        return _deep_to_dict(self._settings)

    def import_from_dict(self, data: dict) -> None:
        self._settings = _deep_from_dict(data)
        self._bus.emit(SettingsChangedEvent(sender="settings", section="*"))
        self.save()
        log.info("Settings imported from dict")
