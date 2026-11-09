"""Gemini 3 tool calls must replay their thoughtSignature; other providers never see it.

Found by the first real-credential buyer chat: Gemini answered the second round of a
tool conversation with HTTP 400 ("Function call is missing a thought_signature"), so
every Playground purchase stopped after the first search. These tests pin the mapping;
the real-provider acceptance run is recorded in docs/STATUS.md.
"""

import asyncio
import copy
from types import SimpleNamespace

from pydantic import SecretStr

from app import ai_providers
from app.ai_providers import (
    GEMINI_SIGNATURE,
    GEMINI_UNSIGNED_PLACEHOLDER,
    PROVIDER_META,
    gemini_blocks,
    gemini_contents,
    without_provider_meta,
)


def candidate(*parts):
    return {"candidates": [{"content": {"role": "model", "parts": list(parts)}}]}


def test_signature_is_kept_on_the_neutral_block_and_thoughts_are_dropped():
    blocks = gemini_blocks(
        candidate(
            {"text": "private reasoning", "thought": True},
            {
                "functionCall": {"name": "search_products", "args": {"query": "tote"}},
                "thoughtSignature": "sig-1",
            },
            {"functionCall": {"name": "search_products", "args": {"query": "scarf"}}},
        )
    )
    assert [b["type"] for b in blocks] == ["tool_use", "tool_use"]
    assert blocks[0][PROVIDER_META] == {GEMINI_SIGNATURE: "sig-1"}
    assert PROVIDER_META not in blocks[1]


def test_replayed_history_returns_each_signature_on_its_own_part():
    blocks = gemini_blocks(
        candidate(
            {
                "functionCall": {"name": "search_products", "args": {"query": "tote"}},
                "thoughtSignature": "sig-call",
            },
        )
    )
    final = gemini_blocks(candidate({"text": "Here it is.", "thoughtSignature": "sig-text"}))
    history = [
        {"role": "user", "content": "Find a tote."},
        {"role": "assistant", "content": blocks},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": blocks[0]["id"], "content": '{"items": []}'}
            ],
        },
        {"role": "assistant", "content": final},
    ]
    contents = gemini_contents(history)
    call_part = contents[1]["parts"][0]
    assert call_part["thoughtSignature"] == "sig-call"
    assert call_part["functionCall"]["name"] == "search_products"
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "search_products"
    assert contents[3]["parts"][0] == {"text": "Here it is.", "thoughtSignature": "sig-text"}


def test_unsigned_history_gets_the_placeholder_only_on_the_first_model_call():
    history = [
        {"role": "user", "content": "Find two things."},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "a", "name": "search_products", "input": {"query": "x"}},
                {"type": "tool_use", "id": "b", "name": "search_products", "input": {"query": "y"}},
            ],
        },
    ]
    parts = gemini_contents(history)[1]["parts"]
    assert parts[0]["thoughtSignature"] == GEMINI_UNSIGNED_PLACEHOLDER
    assert "thoughtSignature" not in parts[1]


def test_provider_meta_is_stripped_without_mutating_stored_history():
    history = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "t",
                    "input": {},
                    PROVIDER_META: {GEMINI_SIGNATURE: "sig"},
                },
            ],
        },
    ]
    before = copy.deepcopy(history)
    cleaned = without_provider_meta(history)
    assert PROVIDER_META not in cleaned[1]["content"][0]
    assert cleaned[0] == {"role": "user", "content": "hi"}
    assert history == before


def test_anthropic_never_receives_gemini_metadata(monkeypatch):
    sent = {}

    class FakeMessages:
        async def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(content=[])

    class FakeClient:
        messages = FakeMessages()

        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(ai_providers.anthropic, "AsyncAnthropic", FakeClient)
    provider = ai_providers.AnthropicProvider(
        SimpleNamespace(anthropic_api_key=SecretStr("k"), anthropic_model="m")
    )
    history = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "t",
                    "input": {},
                    PROVIDER_META: {GEMINI_SIGNATURE: "sig"},
                },
            ],
        },
    ]
    asyncio.run(provider.tool_turn("system", history, [], 100))
    assert PROVIDER_META not in sent["messages"][1]["content"][0]


def test_gemini_tool_turn_sends_the_signature_back_on_the_next_round(monkeypatch):
    bodies = []
    replies = iter(
        [
            candidate(
                {
                    "functionCall": {"name": "search_products", "args": {"query": "tote"}},
                    "thoughtSignature": "sig-round-1",
                }
            ),
            candidate({"text": "Found one."}),
        ]
    )

    async def fake_post(self, body):
        bodies.append(copy.deepcopy(body))
        return next(replies)

    monkeypatch.setattr(ai_providers.GeminiProvider, "_apost", fake_post)
    provider = ai_providers.GeminiProvider(
        SimpleNamespace(gemini_api_key=SecretStr("k"), gemini_model="gemini-test")
    )
    history = [{"role": "user", "content": "Find a tote."}]
    first = asyncio.run(provider.tool_turn("system", history, [], 100))
    history += [
        {"role": "assistant", "content": first},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": first[0]["id"], "content": "{}"}],
        },
    ]
    asyncio.run(provider.tool_turn("system", history, [], 100))
    replayed = bodies[1]["contents"][1]["parts"][0]
    assert replayed["thoughtSignature"] == "sig-round-1"


def test_reasoning_allowance_is_added_on_top_of_the_answer_budget():
    """Real run: "low" reasoning used 1,150 of a 1,200-token listing call (finish MAX_TOKENS)."""
    config = ai_providers.gemini_generation_config(1200, "low")
    allowance = ai_providers.GEMINI_THINKING_ALLOWANCE["low"]
    assert config["maxOutputTokens"] == 1200 + allowance
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert ai_providers.gemini_generation_config(400, None) == {"maxOutputTokens": 400}


def test_every_gemini_request_carries_the_configured_reasoning_level(monkeypatch):
    bodies = []

    async def fake_post(self, body):
        bodies.append(body)
        return candidate({"text": "ok"})

    monkeypatch.setattr(ai_providers.GeminiProvider, "_apost", fake_post)
    provider = ai_providers.GeminiProvider(
        SimpleNamespace(
            gemini_api_key=SecretStr("k"), gemini_model="m", gemini_thinking_level="minimal"
        )
    )
    asyncio.run(provider.tool_turn("s", [{"role": "user", "content": "hi"}], [], 1000))
    asyncio.run(provider.acomplete("s", "hi", 600))
    json_body = provider._body("s", [{"text": "hi"}], 1200, json_output=True)
    for body, budget in zip([*bodies, json_body], (1000, 600, 1200), strict=True):
        config = body["generationConfig"]
        assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
        assert config["maxOutputTokens"] == budget + 256
    assert json_body["generationConfig"]["responseMimeType"] == "application/json"
