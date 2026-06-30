"""Shared UI helpers: design system tokens, button styles, badges, cards, and state widgets."""

from __future__ import annotations

import logging
import time
from typing import Any

import flet as ft

log = logging.getLogger("hard_workers.ui.helpers")


# ── OS Theme Detection ─────────────────────────────────────────────────────────


def detect_os_theme() -> str:
    """Detect the actual OS theme on Windows via registry.

    Returns ``"dark"`` or ``"light"".  Falls back to ``"dark"`` on failure.
    """
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        return "dark"


# ── Design System Tokens ───────────────────────────────────────────────────────


class Colors:
    """Central design token container.

    All colour values are stored as class attributes.  Call
    ``Colors.set_theme("dark"|"light"|"system")`` at startup and whenever
    the user changes the theme preference so that every existing reference
    (including imports held by other modules) resolves to the new palette.
    """

    # ── Brand (shared across themes) ──────────────────────────────────────
    PRIMARY = "#3B82F6"
    PRIMARY_HOVER = "#2563EB"
    SUCCESS = "#22C55E"
    WARNING = "#F59E0B"
    ERROR = "#EF4444"
    SECONDARY = "#8B5CF6"
    ACCENT = "#3B82F6"

    # ── Background (dark defaults) ────────────────────────────────────────
    BG_PAGE = "#0B0F14"
    BG_CHAT = "#0B0F14"
    BG_PANEL = "#111827"
    BG_SURFACE = "#111827"
    BG_SURFACE2 = "#151D29"
    BG_CARD = "#151D29"
    BG_USER_MSG = "#1E293B"
    BG_AI_MSG = "#151D29"
    BG_HOVER = "#1E293B"

    # ── Badge backgrounds (dark defaults) ─────────────────────────────────
    BADGE_CATEGORY = "#1E293B"
    BADGE_MEMORY = "#052E16"
    BADGE_GLOBAL_FACT = "#052E16"
    BADGE_CHAT_FACT = "#172554"
    BADGE_SUMMARY = "#450A0A"

    # ── Agent status badge backgrounds (dark defaults) ────────────────────
    STATUS_THINKING = "#422006"
    STATUS_STREAMING = "#172554"
    STATUS_COMPLETED = "#052E16"
    STATUS_ERROR = "#450A0A"
    STATUS_CANCELLED = "#422006"

    # ── Text hierarchy (dark defaults) ────────────────────────────────────
    TEXT_HIGH = "#F1F5F9"
    TEXT_HIGH2 = "#E2E8F0"
    TEXT_MEDIUM = "#CBD5E1"
    TEXT_MUTED = "#94A3B8"
    TEXT_LOW = "#64748B"
    TEXT_MUTED2 = "#475569"
    TEXT_CODE = "#60A5FA"

    # ── Borders (dark defaults) ───────────────────────────────────────────
    BORDER_DIVIDER = "#1E293B"
    BORDER_CARD = "#263241"
    BORDER_INPUT = "#334155"
    BORDER_FOCUS = "#3B82F6"
    BORDER_GLOBAL_FACT = "#166534"
    BORDER_CHAT_FACT = "#1D4ED8"
    BORDER_CHAT_ROW = "#1E293B"

    # ── Radii (shared) ────────────────────────────────────────────────────
    RADIUS_SM = 4
    RADIUS_MD = 8
    RADIUS_LG = 12
    RADIUS_XL = 16

    # ── Shadow opacity tokens ─────────────────────────────────────────────
    SHADOW_SM = 0.08
    SHADOW_MD = 0.12
    SHADOW_LG = 0.18

    # ── Interaction opacity tokens ────────────────────────────────────────
    OPACITY_HOVER = 0.08
    OPACITY_ACTIVE = 0.12
    OPACITY_DISABLED = 0.38

    # ── Theme palettes ────────────────────────────────────────────────────
    _dark = {
        "BG_PAGE": "#0B0F14",
        "BG_CHAT": "#0B0F14",
        "BG_PANEL": "#111827",
        "BG_SURFACE": "#111827",
        "BG_SURFACE2": "#151D29",
        "BG_CARD": "#151D29",
        "BG_USER_MSG": "#1E293B",
        "BG_AI_MSG": "#151D29",
        "BG_HOVER": "#1E293B",
        "BADGE_CATEGORY": "#1E293B",
        "BADGE_MEMORY": "#052E16",
        "BADGE_GLOBAL_FACT": "#052E16",
        "BADGE_CHAT_FACT": "#172554",
        "BADGE_SUMMARY": "#450A0A",
        "STATUS_THINKING": "#422006",
        "STATUS_STREAMING": "#172554",
        "STATUS_COMPLETED": "#052E16",
        "STATUS_ERROR": "#450A0A",
        "STATUS_CANCELLED": "#422006",
        "TEXT_HIGH": "#F1F5F9",
        "TEXT_HIGH2": "#E2E8F0",
        "TEXT_MEDIUM": "#CBD5E1",
        "TEXT_MUTED": "#94A3B8",
        "TEXT_LOW": "#64748B",
        "TEXT_MUTED2": "#475569",
        "TEXT_CODE": "#60A5FA",
        "BORDER_DIVIDER": "#1E293B",
        "BORDER_CARD": "#263241",
        "BORDER_INPUT": "#334155",
        "BORDER_FOCUS": "#3B82F6",
        "BORDER_GLOBAL_FACT": "#166534",
        "BORDER_CHAT_FACT": "#1D4ED8",
        "BORDER_CHAT_ROW": "#1E293B",
    }

    _light = {
        "BG_PAGE": "#F5F7FA",
        "BG_CHAT": "#F5F7FA",
        "BG_PANEL": "#FFFFFF",
        "BG_SURFACE": "#FFFFFF",
        "BG_SURFACE2": "#EEF2F7",
        "BG_CARD": "#FFFFFF",
        "BG_USER_MSG": "#E8F5E9",
        "BG_AI_MSG": "#FFFFFF",
        "BG_HOVER": "#EEF2F7",
        "BADGE_CATEGORY": "#EEF2F7",
        "BADGE_MEMORY": "#DCFCE7",
        "BADGE_GLOBAL_FACT": "#DCFCE7",
        "BADGE_CHAT_FACT": "#DBEAFE",
        "BADGE_SUMMARY": "#FEE2E2",
        "STATUS_THINKING": "#FEF3C7",
        "STATUS_STREAMING": "#DBEAFE",
        "STATUS_COMPLETED": "#DCFCE7",
        "STATUS_ERROR": "#FEE2E2",
        "STATUS_CANCELLED": "#FEF3C7",
        "TEXT_HIGH": "#0F172A",
        "TEXT_HIGH2": "#1E293B",
        "TEXT_MEDIUM": "#334155",
        "TEXT_MUTED": "#64748B",
        "TEXT_LOW": "#94A3B8",
        "TEXT_MUTED2": "#CBD5E1",
        "TEXT_CODE": "#2563EB",
        "BORDER_DIVIDER": "#E2E8F0",
        "BORDER_CARD": "#D8E1EA",
        "BORDER_INPUT": "#D8E1EA",
        "BORDER_FOCUS": "#2563EB",
        "BORDER_GLOBAL_FACT": "#BBF7D0",
        "BORDER_CHAT_FACT": "#BFDBFE",
        "BORDER_CHAT_ROW": "#E2E8F0",
    }

    _current = "dark"

    @classmethod
    def set_theme(cls, theme: str) -> None:
        """Switch between ``"dark"``, ``"light"``, or ``"system"`` palettes.

        - ``"system"`` resolves to the actual OS theme via ``detect_os_theme()``.
        - All existing ``Colors.X`` references resolve to the new values
          after calling this — no consumer code changes needed.
        """
        if theme == "system":
            theme = detect_os_theme()
        palette = cls._light if theme == "light" else cls._dark
        for key, val in palette.items():
            setattr(cls, key, val)
        cls._current = theme

    @classmethod
    def is_dark(cls) -> bool:
        return cls._current == "dark"

    @staticmethod
    def with_opacity(color: str, opacity: float) -> str:
        return ft.Colors.with_opacity(opacity, color)

    @staticmethod
    def status_color(status: str) -> str:
        mapping = {
            "OK": Colors.SUCCESS,
            "TIMEOUT": Colors.WARNING,
            "UNREACHABLE": Colors.ERROR,
            "ERROR": Colors.ERROR,
        }
        return mapping.get(status, Colors.TEXT_LOW)


def apply_flet_theme(page: ft.Page, theme: str) -> None:
    """Set ``page.theme_mode`` from a ``"dark"`` / ``"light"`` / ``"system"``
    string and update ``Colors`` to the resolved palette."""
    if theme == "light":
        page.theme_mode = ft.ThemeMode.LIGHT
        Colors.set_theme("light")
    elif theme == "system":
        page.theme_mode = ft.ThemeMode.SYSTEM
        Colors.set_theme("system")
    else:
        page.theme_mode = ft.ThemeMode.DARK
        Colors.set_theme("dark")


# ── Style Builders ─────────────────────────────────────────────────────────────


def btn_style(
    color: str | None = None,
    opacity: float = 0.12,
    radius: int | None = None,
) -> ft.ButtonStyle:
    color = color or Colors.PRIMARY
    radius = radius if radius is not None else Colors.RADIUS_MD
    return ft.ButtonStyle(
        bgcolor=ft.Colors.with_opacity(opacity, color),
        color=color,
        shape=ft.RoundedRectangleBorder(radius=radius),
    )


def badge(
    text: str,
    bg_color: str | None = None,
    text_color: str | None = None,
    radius: int | None = None,
) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            text,
            size=10,
            color=text_color or Colors.TEXT_HIGH,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=bg_color or Colors.BADGE_CATEGORY,
        padding=ft.Padding(left=6, right=6, top=2, bottom=2),
        border_radius=radius or Colors.RADIUS_SM,
    )


def card(
    *controls: ft.Control,
    bg_color: str | None = None,
    border_color: str | None = None,
    padding: ft.Padding | None = None,
    border_radius: int | None = None,
    on_hover=None,
    expand: bool | int | None = None,
) -> ft.Container:
    return ft.Container(
        bgcolor=bg_color or Colors.BG_SURFACE2,
        padding=padding or ft.Padding(left=10, right=10, top=8, bottom=8),
        border_radius=border_radius or Colors.RADIUS_MD,
        border=ft.BorderSide(1, border_color or Colors.BORDER_CARD),
        on_hover=on_hover,
        expand=expand,
        content=(
            ft.Row(
                list(controls),
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            if len(controls) != 1 or expand is not None
            else None
        ),
    )


def dialog_title(
    icon: str,
    title: str,
    icon_color: str | None = None,
    extra: ft.Control | None = None,
) -> ft.Row:
    row_content = [
        ft.Icon(icon, color=icon_color or Colors.PRIMARY, size=20),
        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
    ]
    if extra:
        return ft.Row(
            [ft.Row(row_content, spacing=8), extra],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    return ft.Row(row_content, spacing=8)


def status_text(value: str = "", color: str | None = None, size: int = 12) -> ft.Text:
    return ft.Text(value, color=color or Colors.WARNING, size=size)


def section_header(text: str, color: str | None = None) -> ft.Text:
    return ft.Text(
        text,
        size=10,
        weight=ft.FontWeight.BOLD,
        color=color or Colors.PRIMARY,
    )


def divider(color: str | None = None, height: int = 1) -> ft.Divider:
    return ft.Divider(height=height, color=color or Colors.BORDER_DIVIDER)


# ── State Widgets ─────────────────────────────────────────────────────────────


class LoadingIndicator(ft.Row):
    """Inline loading spinner with optional message."""

    def __init__(self, message: str = "Loading\u2026") -> None:
        super().__init__(
            [
                ft.ProgressRing(width=16, height=16),
                ft.Text(message, color=Colors.TEXT_LOW, size=12),
            ],
            spacing=6,
            visible=False,
        )


class EmptyState(ft.Container):
    """Placeholder shown when a list or panel has no data."""

    def __init__(self, message: str = "Nothing here yet.", icon: str | None = None) -> None:
        content = []
        if icon:
            content.append(ft.Icon(icon, color=Colors.TEXT_MUTED2, size=28))
        content.append(
            ft.Text(
                message,
                color=Colors.TEXT_MUTED2,
                size=12,
                text_align=ft.TextAlign.CENTER,
            )
        )
        super().__init__(
            content=ft.Column(
                content,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
