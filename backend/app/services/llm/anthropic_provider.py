from __future__ import annotations

import time

from app.services.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolCallRequest, ToolSpec, Usage


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

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
        anthropic_messages = [self._to_anthropic_message(m) for m in messages]
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]

        response = self._client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        content_text: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in response.content:
            if block.type == "text":
                content_text.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=block.input or {}))

        return LLMResponse(
            content="\n".join(content_text) if content_text else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens
            ),
            model=self._model,
            latency_ms=latency_ms,
        )

    def _to_anthropic_message(self, m: ChatMessage) -> dict:
        if m.role == "tool":
            return {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                ],
            }
        if m.role == "assistant" and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            return {"role": "assistant", "content": blocks}
        # system role messages are passed via the top-level `system` kwarg,
        # never inline -- Anthropic's Messages API has no 'system' message role.
        role = "user" if m.role == "system" else m.role
        return {"role": role, "content": m.content}
