"""Intelligent model router — HardWorkres platform.

Routes user messages to the most appropriate model based on:
- Keyword analysis of the message content
- Workspace category setting
- Model registry category metadata

RouterMode.DISABLED → always use the active model (no routing)
RouterMode.AUTO     → scan message keywords, pick best match
RouterMode.CATEGORY → match workspace category to model category
"""

from __future__ import annotations

import re
import threading

from config.constants import ROUTER_KEYWORDS
from database.repositories import DatabaseManager
from models.domain import ModelRegistryEntry, RouterDecision
from models.enums import ModelCategory, RouterMode
from utils.logging_setup import get_logger

log = get_logger("services.model_router")


class ModelRouterService:
    """Lightweight rule-based model router."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._lock = threading.Lock()
        self._mode = RouterMode.DISABLED
        self._workspace_category: str = ModelCategory.GENERAL

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_mode(self, mode: RouterMode) -> None:
        with self._lock:
            self._mode = mode
        log.info("Router mode set to %r", mode)

    def get_mode(self) -> RouterMode:
        with self._lock:
            return self._mode

    def set_workspace_category(self, category: str) -> None:
        with self._lock:
            self._workspace_category = category

    # ── Routing ───────────────────────────────────────────────────────────────

    def route(
        self,
        message: str,
        fallback_model: str,
    ) -> RouterDecision:
        """Decide which model to use for the given message.

        Always returns a RouterDecision; falls back to *fallback_model* when
        routing is disabled or no match is found.
        """
        with self._lock:
            mode = self._mode
            cat_hint = self._workspace_category

        if mode == RouterMode.DISABLED:
            return RouterDecision(
                chosen_model=fallback_model,
                confidence=1.0,
                detected_category=cat_hint,
                reason="Router disabled — using active model",
            )

        registered = self._db.models.get_all()
        if not registered:
            return RouterDecision(
                chosen_model=fallback_model,
                confidence=0.5,
                detected_category=ModelCategory.GENERAL,
                reason="No registered models — using active model",
            )

        if mode == RouterMode.CATEGORY:
            return self._route_by_category(cat_hint, registered, fallback_model)

        # RouterMode.AUTO
        detected, confidence = self._detect_category(message)
        if confidence == 0.0:
            return RouterDecision(
                chosen_model=fallback_model,
                confidence=0.0,
                detected_category=detected,
                reason="No routing keywords detected — using user-selected model",
            )
        return self._route_by_category(detected, registered, fallback_model, confidence=confidence, auto=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _detect_category(message: str) -> tuple[str, float]:
        """Score message against keyword lists; return best (category, confidence)."""
        text = message.lower()
        words = re.findall(r"\b\w+\b", text)
        word_set = set(words)

        scores: dict[str, float] = {}
        for category, keywords in ROUTER_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in word_set or kw in text)
            if hits:
                scores[category] = hits / len(keywords)

        if not scores:
            return ModelCategory.GENERAL, 0.0

        best_cat = max(scores, key=lambda c: scores[c])
        best_conf = min(scores[best_cat] * 2, 1.0)  # normalise to 0–1
        return best_cat, best_conf

    def _route_by_category(
        self,
        category: str,
        models: list[ModelRegistryEntry],
        fallback: str,
        confidence: float = 1.0,
        auto: bool = False,
    ) -> RouterDecision:
        # Prefer models whose registry category matches
        matches = [m for m in models if str(m.category) == category]
        if not matches:
            # Fall back to General models
            matches = [m for m in models if m.category == ModelCategory.GENERAL]

        if matches:
            chosen = matches[0]
            if auto and category == str(ModelCategory.GENERAL) and confidence < 1.0:
                return RouterDecision(
                    chosen_model=fallback,
                    confidence=confidence,
                    detected_category=category,
                    reason=(
                        f"General detected (confidence {confidence:.0%}) — "
                        f"preferring user selection '{fallback}' over '{chosen.name}'"
                    ),
                )
            reason = (
                f"Auto-detected '{category}' (confidence {confidence:.0%}) → {chosen.name}"
                if auto
                else f"Workspace category '{category}' → {chosen.name}"
            )
            return RouterDecision(
                chosen_model=chosen.name,
                confidence=confidence,
                detected_category=category,
                reason=reason,
            )

        return RouterDecision(
            chosen_model=fallback,
            confidence=confidence * 0.5,
            detected_category=category,
            reason=f"No {category} model found — using active model",
        )
