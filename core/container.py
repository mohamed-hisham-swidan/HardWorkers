"""Lightweight dependency injection container.

Provides a single point of registration and resolution for all
application services.  Services are lazily created (first-access)
and cached as singletons unless ``factory=True`` is passed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger("core.container")


class ServiceNotFound(LookupError):
    """Raised when a requested service is not registered."""


Factory = Callable[["Container"], Any]


class Container:
    """Simple DI container with lazy singleton resolution."""

    def __init__(self) -> None:
        self._registry: dict[str, Factory] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: Factory, *, singleton: bool = True) -> None:
        self._registry[name] = factory
        if not singleton:
            self._instances.pop(name, None)

    def register_instance(self, name: str, instance: Any) -> None:
        self._instances[name] = instance

    def resolve(self, name: str) -> Any:
        if name in self._instances:
            return self._instances[name]
        factory = self._registry.get(name)
        if factory is None:
            raise ServiceNotFound(f"Service {name!r} is not registered")
        instance = factory(self)
        self._instances[name] = instance
        return instance

    def has(self, name: str) -> bool:
        return name in self._instances or name in self._registry

    def clear(self) -> None:
        self._instances.clear()
        self._registry.clear()

    def init(self, config: Any = None) -> None:
        """Minimal initialisation — stores config reference.

        Full bootstrap (registering db, model_router, etc.) is done by
        calling code.  This method exists so the API lifespan hook can
        safely call ``container.init(config)`` without crashing.
        """
        if config is not None:
            self.register_instance("config", config)
            log.info("Container initialised with config")

    def close(self) -> None:
        """Release all managed resources.

        Calls ``close()`` on every cached instance that has one,
        then clears the container.
        """
        for name, instance in self._instances.items():
            if hasattr(instance, "close") and callable(instance.close):
                try:
                    instance.close()
                except Exception as exc:
                    log.debug("Ignored error closing %s: %s", name, exc)
        self.clear()
        log.info("Container closed")
