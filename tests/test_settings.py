"""Tests for settings models and persistence service."""

from __future__ import annotations

from pathlib import Path

from settings.models import (
    ProviderSettings,
    UserSettings,
)
from settings.service import SettingsService, _deep_from_dict, _deep_to_dict


class TestUserSettings:
    def test_defaults(self) -> None:
        us = UserSettings.defaults()
        assert us.general.language == "en"
        assert us.appearance.theme == "dark"
        assert us.providers.ollama.base_url == "http://localhost:11434"

    def test_custom_values(self) -> None:
        us = UserSettings.defaults()
        us.appearance.theme = "light"
        assert us.appearance.theme == "light"


class TestSerializeRoundTrip:
    def test_round_trip(self, tmp_path: Path) -> None:
        original = UserSettings.defaults()
        original.general.language = "fr"
        original.appearance.window_width = 1920

        d = _deep_to_dict(original)
        restored = _deep_from_dict(d)

        assert restored.general.language == "fr"
        assert restored.appearance.window_width == 1920


class TestSettingsService:
    def test_load_defaults(self, tmp_path: Path) -> None:
        from core.events import EventBus

        bus = EventBus()
        path = tmp_path / "settings.json"
        svc = SettingsService(bus, path=str(path))
        us = svc.load()

        assert us.general.language == "en"
        assert svc.current is us

    def test_save_and_reload(self, tmp_path: Path) -> None:
        from core.events import EventBus

        bus = EventBus()
        path = tmp_path / "settings.json"
        svc = SettingsService(bus, path=str(path))
        svc.load()

        svc.set_general(language="de")
        svc.set_appearance(window_width=1600)

        svc2 = SettingsService(bus, path=str(path))
        us2 = svc2.load()

        assert us2.general.language == "de"
        assert us2.appearance.window_width == 1600

    def test_reset(self, tmp_path: Path) -> None:
        from core.events import EventBus

        bus = EventBus()
        path = tmp_path / "settings.json"
        svc = SettingsService(bus, path=str(path))
        svc.load()

        svc.set_general(language="ja")
        svc.reset()

        assert svc.current.general.language == "en"


class TestProviders:
    def test_all_providers_present(self) -> None:
        p = ProviderSettings()
        assert hasattr(p, "ollama")
        assert hasattr(p, "openai")
        assert hasattr(p, "anthropic")
        assert hasattr(p, "gemini")
        assert hasattr(p, "groq")
        assert hasattr(p, "openrouter")
        assert hasattr(p, "together")
        assert hasattr(p, "deepseek")
