"""Core abstractions: interfaces, event bus, DI container, config validation."""

from core.container import Container
from core.events import Event, EventBus
from core.interfaces import (
    ChatRepositoryProtocol,
    MemoryServiceProtocol,
    ModelManagerProtocol,
    ModelRouterProtocol,
    RepositoryProtocol,
    SummarizationServiceProtocol,
    VectorStoreProtocol,
    WorkspaceServiceProtocol,
)

__all__ = [
    "Container",
    "Event",
    "EventBus",
    "ChatRepositoryProtocol",
    "MemoryServiceProtocol",
    "ModelManagerProtocol",
    "ModelRouterProtocol",
    "RepositoryProtocol",
    "SummarizationServiceProtocol",
    "VectorStoreProtocol",
    "WorkspaceServiceProtocol",
]
