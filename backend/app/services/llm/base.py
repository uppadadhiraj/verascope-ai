"""Provider-agnostic LLM interface.

Every agent talks to `LLMProvider`, never to `anthropic`/`openai`/`httpx`
directly -- that's what keeps "the model provider should be configurable"
(section 6) true in practice instead of just in the README.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: Role
    content: str
    tool_call_id: str | None = None
    """Set on role='tool' messages: which tool_calls[].id this is answering."""
    name: str | None = None
    """Set on role='tool' messages: the tool name (some providers want it)."""
    tool_calls: list["ToolCallRequest"] = field(default_factory=list)
    """Set on role='assistant' messages that requested tool calls, when
    replaying history back to the provider."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    """JSON Schema for the tool's arguments object."""


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    usage: Usage
    model: str
    latency_ms: int


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse: ...
