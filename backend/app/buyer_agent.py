"""Budget-bound chat through the normal remote MCP SDK client, with explicit confirmation."""

import asyncio
import copy
import json
import uuid
from datetime import timedelta

from mcp import Client
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app import llm, paypal
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.guards import parse_id
from app.listing_workflow import caption_text
from app.models import AgentSession, Quote, RateBucket, utcnow


def acquire(session_id, message, confirmation):
    # No buyer address, credentials or contact information is sent to the model.
    message = caption_text(message)
    token = uuid.uuid4()
    with session_factory() as db, db.begin():
        session = db.scalar(
            select(AgentSession).where(AgentSession.id == session_id).with_for_update()
        )
        if not session:
            raise DomainError("SESSION_NOT_FOUND", "Start a new shopping session.", 404)
        now = utcnow()
        if session.chat_lease_until and session.chat_lease_until > now:
            raise DomainError(
                "CHAT_BUSY", "Wait for the current reply before sending another.", 409
            )
        key = f"chat:{session_id}"
        db.execute(
            insert(RateBucket)
            .values(key=key, used=0, expires_at=now + timedelta(minutes=1))
            .on_conflict_do_nothing()
        )
        bucket = db.scalar(select(RateBucket).where(RateBucket.key == key).with_for_update())
        if bucket.expires_at <= now:
            bucket.used, bucket.expires_at = 0, now + timedelta(minutes=1)
        if bucket.used >= 20:
            raise DomainError("RATE_LIMITED", "You can send 20 messages per minute.", 429)
        if confirmation:
            quote = db.get(Quote, confirmation)
            if (
                not quote
                or session.pending_quote_id != confirmation
                or quote.agent_session_id != session_id
                or quote.expires_at <= now
            ):
                raise DomainError(
                    "CONFIRMATION_INVALID", "Request and review a fresh quote before checkout.", 409
                )
        bucket.used += 1
        session.chat_lease, session.chat_lease_until = token, now + timedelta(seconds=90)
        return {
            "token": token,
            "history": copy.deepcopy(session.chat_history),
            "budget": paypal.money(session.budget_minor),
            "message": message,
        }


def finish(session_id, state, history, pending):
    with session_factory() as db, db.begin():
        session = db.scalar(
            select(AgentSession).where(AgentSession.id == session_id).with_for_update()
        )
        if session and session.chat_lease == state["token"]:
            history = history[-24:]
            while history and not (
                history[0]["role"] == "user" and isinstance(history[0]["content"], str)
            ):
                history.pop(0)
            session.chat_history = history
            session.pending_quote_id = pending
            session.chat_lease = session.chat_lease_until = None


def quote_review(session_id, quote_id):
    with session_factory() as db:
        quote = db.get(Quote, parse_id(quote_id))
        if not quote or quote.agent_session_id != session_id:
            raise DomainError("QUOTE_NOT_FOUND", "This quote is unavailable.", 404)
        return {
            "quote_id": str(quote.id),
            "title": quote.title,
            "qty": quote.qty,
            "total": paypal.money(quote.total_minor),
            "shipping": paypal.money(quote.shipping_minor),
            "currency": quote.currency,
            "expires_at": quote.expires_at.isoformat(),
            "ship_to_country": quote.ship_to_country,
        }


async def events(session_id, state, country, confirmation=None):
    history = state["history"]
    safe_history = copy.deepcopy(history)
    pending = confirmation
    history.append({"role": "user", "content": state["message"] or "Confirm the displayed quote."})
    try:
        async with asyncio.timeout(60), Client(get_settings().public_api_url + "/mcp") as client:
            if confirmation:
                args = {"quote_id": str(confirmation), "session_id": str(session_id)}
                yield {
                    "type": "tool_call",
                    "name": "create_checkout",
                    "arguments": {"quote_id": str(confirmation)},
                }
                result = await client.call_tool("create_checkout", args)
                data = result.structured_content
                if not isinstance(data, dict):
                    raise DomainError(
                        "MCP_UNAVAILABLE", "The checkout result could not be read.", 503
                    )
                yield {"type": "tool_result", "name": "create_checkout", "result": data}
                if "error" not in data:
                    yield {"type": "checkout", **data}
                    pending = None
                else:
                    yield {"type": "error", "error": data["error"]}
            else:
                discovered = await client.list_tools()
                tools = []
                for tool in discovered.tools:
                    if tool.name not in {"search_products", "get_quote", "get_order_status"}:
                        continue
                    schema = copy.deepcopy(tool.input_schema)
                    schema.get("properties", {}).pop("session_id", None)
                    schema["required"] = [
                        key for key in schema.get("required", []) if key != "session_id"
                    ]
                    tools.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": schema,
                        }
                    )
                for _ in range(6):
                    blocks = await llm.buyer_turn(history, tools, state["budget"], country)
                    # Only text and tool_use blocks are persisted; no provider reasoning blocks.
                    blocks = [b for b in blocks if b.get("type") in {"text", "tool_use"}]
                    history.append({"role": "assistant", "content": blocks})
                    uses = [b for b in blocks if b["type"] == "tool_use"]
                    for block in blocks:
                        if block["type"] == "text":
                            yield {"type": "message", "text": block["text"]}
                    if not uses:
                        safe_history = copy.deepcopy(history)
                        break
                    if len(uses) > 4:
                        raise DomainError("AGENT_LIMIT", "Try a simpler shopping request.")
                    results = []
                    for use in uses:
                        name, args = use["name"], copy.deepcopy(use["input"])
                        if name not in {"search_products", "get_quote", "get_order_status"}:
                            data = DomainError(
                                "CONFIRMATION_REQUIRED",
                                "The human must confirm the displayed quote.",
                            ).payload()
                        else:
                            args.pop("session_id", None)
                            if name != "search_products":
                                args["session_id"] = str(session_id)
                            if name in {"search_products", "get_quote"}:
                                args["ship_to_country"] = country
                            yield {
                                "type": "tool_call",
                                "name": name,
                                "arguments": {k: v for k, v in args.items() if k != "session_id"},
                            }
                            result = await client.call_tool(name, args)
                            data = result.structured_content
                            if not isinstance(data, dict):
                                raise DomainError(
                                    "MCP_UNAVAILABLE", "A tool result could not be read.", 503
                                )
                        yield {"type": "tool_result", "name": name, "result": data}
                        if name == "get_quote" and "quote_id" in data and "error" not in data:
                            review = await asyncio.to_thread(
                                quote_review, session_id, data["quote_id"]
                            )
                            pending = uuid.UUID(review["quote_id"])
                            yield {"type": "quote", **review}
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": use["id"],
                                "content": json.dumps(model_data(data)),
                            }
                        )
                    history.append({"role": "user", "content": results})
                    safe_history = copy.deepcopy(history)
                else:
                    yield {
                        "type": "error",
                        "error": {
                            "code": "AGENT_LIMIT",
                            "message": "Try a simpler shopping request.",
                        },
                    }
    except DomainError as exc:
        yield {"type": "error", **exc.payload()}
    except Exception:
        # Do not expose provider responses, tokens or internal errors over SSE.
        yield {
            "type": "error",
            "error": {
                "code": "CHAT_UNAVAILABLE",
                "message": "Chat is unavailable. Try the catalog explorer.",
            },
        }
    finally:
        await asyncio.to_thread(finish, session_id, state, safe_history, pending)
    yield {"type": "done"}


def model_data(data):
    if isinstance(data, list):
        return [model_data(item) for item in data]
    if not isinstance(data, dict):
        return data
    clean = {}
    for key, value in data.items():
        if key in {"image_url", "product_url", "ship_to", "email", "address"}:
            continue
        if key in {"title", "description", "store_name"} and isinstance(value, str):
            try:
                value = caption_text(value)
            except DomainError:
                value = "Untrusted personal or instruction text removed."
        clean[key] = model_data(value)
    return clean
