"""Interchangeable model providers (Strategy pattern) behind one small interface.

Providers only translate a provider-neutral request into one HTTP exchange and return
plain text or neutral content blocks. Policy (prompts, schema validation, retries,
safety filters and public error messages) stays in ``app.llm`` so adding a provider
never touches commerce rules (Open/Closed). Each provider makes exactly one attempt;
durable jobs own transport retries.
"""

import base64
import json
from dataclasses import dataclass
from typing import Protocol

import anthropic
import httpx

REQUEST_TIMEOUT_SECONDS = 30
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class AudioPart:
    data: bytes
    mime_type: str = "audio/ogg"


Part = TextPart | ImagePart | AudioPart


class ProviderUnavailable(Exception):
    """A transport, quota or server failure; never carries provider text to users."""


class ModelProvider(Protocol):
    """The minimum each provider must implement (Interface Segregation)."""

    name: str

    def complete(
        self, system: str, parts: list[Part], max_tokens: int, json_output: bool = False
    ) -> str: ...

    async def acomplete(self, system: str, text: str, max_tokens: int) -> str: ...

    async def tool_turn(
        self, system: str, messages: list, tools: list, max_tokens: int
    ) -> list[dict]: ...


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings):
        self._key = settings.anthropic_api_key.get_secret_value()
        self._model = settings.anthropic_model

    def _options(self):
        return {"api_key": self._key, "timeout": REQUEST_TIMEOUT_SECONDS, "max_retries": 0}

    @staticmethod
    def content(parts: list[Part]) -> list[dict]:
        blocks = []
        for part in parts:
            if isinstance(part, ImagePart):
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part.mime_type,
                            "data": _b64(part.data),
                        },
                    }
                )
            elif isinstance(part, AudioPart):
                payload = {"mime_type": part.mime_type, "audio_base64": _b64(part.data)}
                blocks.append({"type": "text", "text": json.dumps(payload)})
            else:
                blocks.append({"type": "text", "text": part.text})
        return blocks

    @staticmethod
    def _text(response) -> str:
        return "".join(block.text for block in response.content if block.type == "text")

    def complete(self, system, parts, max_tokens, json_output=False):
        try:
            with anthropic.Anthropic(**self._options()) as client:
                response = client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": self.content(parts)}],
                )
            return self._text(response)
        except anthropic.APIError as exc:
            raise ProviderUnavailable(self.name) from exc

    async def acomplete(self, system, text, max_tokens):
        try:
            async with anthropic.AsyncAnthropic(**self._options()) as client:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": text}],
                )
            return self._text(response)
        except anthropic.APIError as exc:
            raise ProviderUnavailable(self.name) from exc

    async def tool_turn(self, system, messages, tools, max_tokens):
        try:
            async with anthropic.AsyncAnthropic(**self._options()) as client:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    tools=tools,
                )
            return [block.model_dump(exclude_none=True) for block in response.content]
        except anthropic.APIError as exc:
            raise ProviderUnavailable(self.name) from exc


def gemini_schema(schema: dict) -> dict:
    """Reduce JSON Schema properties to the subset Gemini functionDeclarations accept."""
    props = {}
    for key, val in (schema.get("properties") or {}).items():
        if isinstance(val, dict):
            clean_prop = {k: v for k, v in val.items() if k in {"type", "description", "enum"}}
            clean_prop.setdefault("type", "string")
            props[key] = clean_prop
    out = {"type": "object", "properties": props}
    if schema.get("required"):
        out["required"] = [r for r in schema["required"] if r in props]
    return out


def gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


def gemini_contents(messages) -> list[dict]:
    """Map neutral (Anthropic-shaped) chat history to Gemini contents."""
    tool_names: dict[str, str] = {}
    contents = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        raw_content = msg.get("content")
        if isinstance(raw_content, str):
            contents.append({"role": role, "parts": [{"text": raw_content}]})
            continue
        parts = []
        for block in raw_content or []:
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                parts.append({"text": block["text"]})
            elif btype == "tool_use":
                tool_names[block["id"]] = block["name"]
                parts.append(
                    {"functionCall": {"name": block["name"], "args": block.get("input") or {}}}
                )
            elif btype == "tool_result":
                name = tool_names.get(block.get("tool_use_id", ""), "mcp_tool")
                try:
                    parsed = json.loads(block.get("content") or "{}")
                except ValueError:
                    parsed = {"raw": str(block.get("content") or "")}
                response = parsed if isinstance(parsed, dict) else {"items": parsed}
                parts.append({"functionResponse": {"name": name, "response": response}})
        if parts:
            contents.append({"role": role, "parts": parts})
    return contents


def gemini_tool_payload(messages, tools, system_text: str, max_tokens: int = 1000) -> dict:
    declarations = [
        {
            "name": t["name"],
            "description": t.get("description") or "",
            "parameters": gemini_schema(t.get("input_schema") or {}),
        }
        for t in tools
    ]
    body = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": gemini_contents(messages),
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if declarations:
        body["tools"] = [{"functionDeclarations": declarations}]
    return body


def gemini_blocks(payload: dict) -> list[dict]:
    """Map a Gemini candidate back to neutral text/tool_use blocks."""
    candidates = payload.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    blocks = []
    for idx, part in enumerate(parts):
        if part.get("text"):
            blocks.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            call = part["functionCall"]
            blocks.append(
                {
                    "type": "tool_use",
                    "id": f"gemini_call_{idx}_{call.get('name', 'tool')}",
                    "name": call.get("name", ""),
                    "input": dict(call.get("args") or {}),
                }
            )
    return blocks


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings):
        self._key = settings.gemini_api_key.get_secret_value()
        self._url = GEMINI_ENDPOINT.format(model=settings.gemini_model)

    def _headers(self):
        return {"Content-Type": "application/json", "X-goog-api-key": self._key}

    @staticmethod
    def parts(parts: list[Part]) -> list[dict]:
        out = []
        for part in parts:
            if isinstance(part, ImagePart | AudioPart):
                out.append({"inline_data": {"mime_type": part.mime_type, "data": _b64(part.data)}})
            else:
                out.append({"text": part.text})
        return out

    @staticmethod
    def _body(system, parts, max_tokens, json_output=False):
        config = {"maxOutputTokens": max_tokens}
        if json_output:
            config = {"responseMimeType": "application/json", **config}
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": config,
        }

    def complete(self, system, parts, max_tokens, json_output=False):
        body = self._body(system, self.parts(parts), max_tokens, json_output)
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.post(self._url, headers=self._headers(), json=body)
                response.raise_for_status()
                return gemini_text(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(self.name) from exc

    async def _apost(self, body):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(self._url, headers=self._headers(), json=body)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(self.name) from exc

    async def acomplete(self, system, text, max_tokens):
        return gemini_text(await self._apost(self._body(system, [{"text": text}], max_tokens)))

    async def tool_turn(self, system, messages, tools, max_tokens):
        payload = await self._apost(gemini_tool_payload(messages, tools, system, max_tokens))
        try:
            return gemini_blocks(payload)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderUnavailable(self.name) from exc


# Order is preference: the first configured provider wins.
PROVIDERS = (
    ("anthropic_api_key", AnthropicProvider),
    ("gemini_api_key", GeminiProvider),
)


def configured(settings) -> bool:
    return any(getattr(settings, field, None) for field, _ in PROVIDERS)


def select(settings) -> ModelProvider | None:
    """Factory: build the preferred configured provider, or None when none is set."""
    for field, provider in PROVIDERS:
        if getattr(settings, field, None):
            return provider(settings)
    return None
