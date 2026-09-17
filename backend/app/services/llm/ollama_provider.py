"""Local model provider via Ollama's REST API (http://localhost:11434).

Tool-calling support depends on the underlying model (e.g. llama3.1+,
qwen2.5) -- Ollama's /api/chat accepts an OpenAI-style `tools` array and
returns `message.tool_calls` the same shape when the model supports it.
Models without tool-calling training will simply never emit tool_calls;
agents built on this provider should treat that as "no tool call requested"
rather than an error.
"""
from __future__ import annotations

import time

import httpx

from app.services.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolCallRequest, ToolSpec, Usage


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=120.0)

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        start = time.monotonic()
        ollama_messages: list[dict] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(self._to_ollama_message(m) for m in messages)

        payload: dict = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]

        resp = self._client.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)

        message = data.get("message", {})
        tool_calls: list[ToolCallRequest] = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function", {})
            tool_calls.append(
                ToolCallRequest(id=f"call_{i}", name=fn.get("name", ""), arguments=fn.get("arguments", {}) or {})
            )

        return LLMResponse(
            content=message.get("content") or None,
            tool_calls=tool_calls,
            stop_reason="tool_use" if tool_calls else "end_turn",
            usage=Usage(
                input_tokens=data.get("prompt_eval_count", 0), output_tokens=data.get("eval_count", 0)
            ),
            model=self._model,
            latency_ms=latency_ms,
        )

    def _to_ollama_message(self, m: ChatMessage) -> dict:
        if m.role == "tool":
            return {"role": "tool", "content": m.content}
        if m.role == "assistant" and m.tool_calls:
            return {
                "role": "assistant",
                "content": m.content or "",
                "tool_calls": [
                    {"function": {"name": tc.name, "arguments": tc.arguments}} for tc in m.tool_calls
                ],
            }
        return {"role": m.role, "content": m.content}
