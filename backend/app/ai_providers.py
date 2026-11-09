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

# Gemini 3 spends output tokens on reasoning before answering. With the answer budgets
# sized for visible text (400-1,200 tokens), "low" reasoning alone consumed 1,150 of a
# 1,200-token listing call and truncated the JSON. Each level gets its own allowance on
# top of the caller's answer budget; only tokens actually generated are billed.
GEMINI_THINKING_ALLOWANCE = {"minimal": 256, "low": 2048, "medium": 4096, "high": 8192}


def gemini_generation_config(max_tokens: int, thinking_level: str | None) -> dict:
    """Answer budget plus the reasoning allowance for the configured level."""
    if not thinking_level:
        return {"maxOutputTokens": max_tokens}
    return {
        "maxOutputTokens": max_tokens + GEMINI_THINKING_ALLOWANCE[thinking_level],
        "thinkingConfig": {"thinkingLevel": thinking_level},
    }


# Provider-private data a neutral block must carry between turns. It is stored with the
# chat history and stripped before any other provider sees the block.
PROVIDER_META = "provider_meta"
GEMINI_SIGNATURE = "gemini_thought_signature"
# Gemini 3 rejects a current-turn functionCall without its thoughtSignature. History that
# no Gemini model produced (another provider, or sessions stored before signatures were
# kept) uses the documented placeholder, which Gemini accepts in place of a signature.
GEMINI_UNSIGNED_PLACEHOLDER = "skip_thought_signature_validator"


def without_provider_meta(messages: list) -> list:
    """Copy of neutral messages with provider-private block metadata removed."""
    cleaned = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            content = [
                {k: v for k, v in block.items() if k != PROVIDER_META}
                if isinstance(block, dict)
                else block
                for block in content
            ]
        cleaned.append({**msg, "content": content})
    return cleaned


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
                    messages=without_provider_meta(messages),
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
        first_call = True
        for block in raw_content or []:
            btype = block.get("type")
            signature = (block.get(PROVIDER_META) or {}).get(GEMINI_SIGNATURE)
            if btype == "text" and block.get("text"):
                part = {"text": block["text"]}
                if signature:
                    part["thoughtSignature"] = signature
                parts.append(part)
            elif btype == "tool_use":
                tool_names[block["id"]] = block["name"]
                part = {"functionCall": {"name": block["name"], "args": block.get("input") or {}}}
                if signature:
                    part["thoughtSignature"] = signature
                elif first_call and role == "model":
                    part["thoughtSignature"] = GEMINI_UNSIGNED_PLACEHOLDER
                first_call = False
                parts.append(part)
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


def gemini_tool_payload(
    messages, tools, system_text: str, max_tokens: int = 1000, thinking_level: str | None = None
) -> dict:
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
        "generationConfig": gemini_generation_config(max_tokens, thinking_level),
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
        if part.get("thought"):
            continue  # thought summaries are never shown or replayed
        if part.get("text"):
            block = {"type": "text", "text": part["text"]}
        elif "functionCall" in part:
            call = part["functionCall"]
            block = {
                "type": "tool_use",
                "id": f"gemini_call_{idx}_{call.get('name', 'tool')}",
                "name": call.get("name", ""),
                "input": dict(call.get("args") or {}),
            }
        else:
            continue
        if part.get("thoughtSignature"):
            block[PROVIDER_META] = {GEMINI_SIGNATURE: part["thoughtSignature"]}
        blocks.append(block)
    return blocks


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings):
        self._key = settings.gemini_api_key.get_secret_value()
        self._url = GEMINI_ENDPOINT.format(model=settings.gemini_model)
        self._thinking = getattr(settings, "gemini_thinking_level", None)

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

    def _body(self, system, parts, max_tokens, json_output=False):
        config = gemini_generation_config(max_tokens, self._thinking)
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
        payload = await self._apost(
            gemini_tool_payload(messages, tools, system, max_tokens, self._thinking)
        )
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
