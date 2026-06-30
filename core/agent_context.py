"""Agent context — the immutable input to every agent invocation.

All data an agent needs to execute is packaged into a single
:class:`AgentContext` object.  Sub-contexts provide scoped access to
conversation history, workspace configuration, memory facts, and token
budgets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationContext:
    """The current conversation turn plus history.

    Fields:
        system_prompt: System-level instruction for the LLM.
        messages: Prior conversation history as ``[{"role": ..., "content": ...}, ...]``.
        user_message: The current user input text.
        image_base64: Optional base64-encoded image attached to the user message.
    """

    system_prompt: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    user_message: str = ""
    image_base64: str | None = None


@dataclass(frozen=True)
class WorkspaceContext:
    """Workspace-scoped configuration.

    Immutable — cannot be modified during an invocation.
    """

    model: str = ""


@dataclass
class MemoryContext:
    """Semantic memory facts retrieved for this invocation.

    Fields:
        facts: List of ``{"key": ..., "value": ..., "score": ...}`` dicts.
    """

    facts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TokenBudget:
    """Token limits for the invocation.

    Fields:
        max_input_tokens: Upper bound for the assembled context.
        max_output_tokens: Upper bound for the generated response.
        max_total_tokens: Combined input + output limit.
    """

    max_input_tokens: int = 32_000
    max_output_tokens: int = 4_096
    max_total_tokens: int = 36_096


@dataclass
class AgentContext:
    """Complete context for a single agent invocation.

    Fields:
        invocation_id: Unique identifier for this invocation (UUID4 hex).
        conversation: The conversation turn and history.
        workspace: The active workspace configuration.
        memory: Retrieved semantic memory facts.
        token_budget: Token limits for this invocation.
        metadata: Arbitrary key-value pairs for observability / routing.
    """

    conversation: ConversationContext = field(default_factory=ConversationContext)
    workspace: WorkspaceContext = field(default_factory=WorkspaceContext)
    memory: MemoryContext = field(default_factory=MemoryContext)
    token_budget: TokenBudget = field(default_factory=TokenBudget)
    metadata: dict[str, Any] = field(default_factory=dict)
    invocation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
