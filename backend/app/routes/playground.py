import asyncio
import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import buyer_agent
from app.config import get_settings
from app.errors import DomainError

router = APIRouter()


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: uuid.UUID
    message: str = Field(default="", max_length=600)
    ship_to_country: str = Field(pattern="^(US|GB)$")
    confirmed_quote_id: uuid.UUID | None = None


@router.post("/api/playground/chat")
async def chat(body: ChatInput):
    if not get_settings().anthropic_api_key and not body.confirmed_quote_id:
        raise DomainError(
            "AI_NOT_CONFIGURED", "AI chat is unavailable. Use the catalog explorer.", 503
        )
    state = await asyncio.to_thread(
        buyer_agent.acquire, body.session_id, body.message, body.confirmed_quote_id
    )

    async def stream():
        async for event in buyer_agent.events(
            body.session_id, state, body.ship_to_country, body.confirmed_quote_id
        ):
            yield "data: " + json.dumps(event) + "\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
