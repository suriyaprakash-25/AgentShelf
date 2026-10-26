"""Explicit seller command states. No model can authorize account access or money."""

import re
import uuid
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import String, cast, select
from sqlalchemy.dialects.postgresql import insert

from app import auth, copilot, listing_workflow, llm, paypal, tracking, whatsapp
from app.config import get_settings
from app.errors import DomainError
from app.guards import safe_text
from app.models import Conversation, Job, ListingRequest, Order, Product, Seller, utcnow
from app.routes.sellers import OnboardingInput, TrackingInput

HELP = (
    "Send a product photo to draft a listing. Set price 45 and stock 3, then YES. "
    "Edit live items: price 45 #12, stock 0 #12, remove #12. "
    "Use orders or track #ORDER DHL NUMBER. Use dashboard to sign in, or help."
)


def reply(db, source, phone, text):
    db.execute(
        insert(Job)
        .values(
            kind="whatsapp_send",
            dedupe_key=f"reply:{source}",
            payload={"phone": phone, "text": text},
            status="queued",
            attempts=0,
        )
        .on_conflict_do_nothing()
    )


def process(db, job):
    message = job.payload
    phone = message.get("from")
    if not isinstance(phone, str) or not re.fullmatch(r"\d{7,20}", phone):
        raise DomainError("INVALID_SENDER", "Invalid WhatsApp sender.")
    db.execute(
        insert(Conversation)
        .values(whatsapp_phone=phone, state="new", context={})
        .on_conflict_do_nothing()
    )
    conversation = db.scalar(
        select(Conversation).where(Conversation.whatsapp_phone == phone).with_for_update()
    )
    older = db.scalar(
        select(Job.id)
        .where(
            Job.kind == "whatsapp_message",
            Job.status == "queued",
            Job.payload["from"].astext == phone,
            Job.created_at < job.created_at,
        )
        .limit(1)
    )
    if older:
        raise DomainError("CHANNEL_ORDER_WAIT", "An earlier seller message must finish first.", 409)
    seller = db.scalar(
        select(Seller).where(Seller.whatsapp_phone == phone, Seller.status == "active")
    )
    text = message.get("text", {}).get("body", "").strip()
    if len(text) > 600:
        reply(db, job.id, phone, "Use a message of 600 characters or fewer.")
        return
    try:
        if not seller:
            result = onboard(conversation, text, phone)
        else:
            result = command(db, conversation, seller, message, text)
    except (DomainError, ValidationError) as exc:
        if isinstance(exc, DomainError) and exc.status >= 500:
            raise
        result = (
            exc.message
            if isinstance(exc, DomainError)
            else "Check the details and try again. Type help for commands."
        )
    reply(db, job.id, phone, result)


def onboard(conversation, text, phone):
    context = dict(conversation.context)
    state = conversation.state
    if text.lower() in {"help", "restart"} or state not in {
        "name",
        "country",
        "email",
        "paypal",
        "consent",
    }:
        conversation.state, conversation.context = "name", {}
        return (
            "Welcome to AgentShelf. We verify your email before connecting this phone to a store. "
            "What is your store name? Reply with the name only."
        )
    if state == "name":
        if not 2 <= len(text) <= 100:
            return "Use a store name of 2 to 100 characters."
        context["name"] = safe_text(text, 100)
        conversation.state = "country"
        result = (
            "What is your merchant country? Send a two-letter country code, for example IN. "
            "Payment eligibility is checked separately."
        )
    elif state == "country":
        if not re.fullmatch(r"[A-Za-z]{2}", text):
            return "Send a two-letter country code."
        context["country"] = text.upper()
        conversation.state = "email"
        result = "What email should receive your store sign-in link?"
    elif state in {"email", "paypal"}:
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", text) or len(text) > 254:
            return "Send a valid email address."
        context["email" if state == "email" else "paypal_email"] = text.lower()
        conversation.state = "paypal" if state == "email" else "consent"
        result = (
            "What is your PayPal business email?"
            if state == "email"
            else (
                "Reply YES to confirm your store details and consent to storing them and "
                "connecting this WhatsApp phone after email verification. "
                "Initial shipping is US/UK in USD. Payment receiving remains subject to "
                "merchant eligibility. Reply restart to correct details."
            )
        )
    else:
        if text.upper() != "YES":
            return "Reply YES to consent, or restart to correct your details."
        data = OnboardingInput(**context, consent=True)
        profile = {
            "name": data.name,
            "country": data.country,
            "paypal_email": data.paypal_email,
            "whatsapp_phone": phone,
        }
        auth.request_link(data.email, profile, "meta:" + phone)
        conversation.state, conversation.context = "awaiting_email", {}
        return (
            "Check your email and open the single-use link to verify your store. "
            "Then send help here to get your store and MCP links."
        )
    conversation.context = context
    return result


def command(db, conversation, seller, message, text):
    context = dict(conversation.context)
    if message.get("type") in {"audio", "voice"}:
        audio = message.get("audio") or message.get("voice") or {}
        raw_audio = whatsapp.download_audio(audio.get("id"))
        mime = audio.get("mime_type") or "audio/ogg"
        transcript = listing_workflow.caption_text(llm.transcribe_voice_note(raw_audio, mime))
        if conversation.state == "awaiting_draft" and context.get("listing_id"):
            pending = db.scalar(
                select(ListingRequest)
                .where(
                    ListingRequest.id == uuid.UUID(context["listing_id"]),
                    ListingRequest.seller_id == seller.id,
                )
                .with_for_update()
            )
            if pending and pending.status == "queued":
                pending.caption = listing_workflow.caption_text(
                    ((pending.caption or "") + " " + transcript).strip()
                )
                return "Voice note transcribed and added to your queued listing draft."
        context["voice_caption"] = transcript
        conversation.context = context
        return (
            "Voice note transcribed. Send one to four product photos to draft your listing "
            "with this description."
        )
    if message.get("type") == "image":
        image = message.get("image", {})
        raw_caption = image.get("caption", "")
        if context.get("voice_caption"):
            raw_caption = (context.pop("voice_caption") + " " + raw_caption).strip()
        caption = listing_workflow.caption_text(raw_caption)
        identifier = uuid.uuid5(uuid.NAMESPACE_URL, "agentshelf:meta:" + message["id"])
        asset = listing_workflow.upload(
            seller.id, whatsapp.download_image(image.get("id")), identifier
        )
        if conversation.state == "awaiting_draft" and context.get("listing_id"):
            pending = db.scalar(
                select(ListingRequest)
                .where(
                    ListingRequest.id == uuid.UUID(context["listing_id"]),
                    ListingRequest.seller_id == seller.id,
                )
                .with_for_update()
            )
            if (
                pending
                and pending.status == "queued"
                and pending.created_at > utcnow() - timedelta(seconds=8)
                and len(pending.media_ids) < 4
            ):
                pending.media_ids = list(dict.fromkeys([*pending.media_ids, asset["id"]]))
                if caption:
                    pending.caption = listing_workflow.caption_text(
                        (pending.caption + " " + caption).strip()
                    )
                draft_job = db.scalar(
                    select(Job)
                    .where(Job.dedupe_key == f"listing:{pending.id}")
                    .with_for_update(skip_locked=True)
                )
                if draft_job:
                    draft_job.run_after = min(
                        utcnow() + timedelta(seconds=2), pending.created_at + timedelta(seconds=8)
                    )
                return (
                    "Photo added to your draft (up to four). Wait for review before replying YES."
                )
        result = listing_workflow.create(
            seller.id, [uuid.UUID(asset["id"])], caption, identifier, seller.whatsapp_phone
        )
        conversation.state, conversation.context = "awaiting_draft", {"listing_id": result["id"]}
        return (
            "Your photo is queued. Send up to four product photos together. "
            "Nothing publishes until you set price and stock "
            "and reply YES."
        )
    if text.lower() in {"help", "dashboard"}:
        return (
            HELP
            + f" Store: {get_settings().frontend_url}/s/{seller.store_slug}. "
            + f"MCP: {get_settings().public_api_url}/mcp. "
            + f"Dashboard: {get_settings().frontend_url}/dashboard."
        )
    if text.lower() in {"summary", "copilot summary"}:
        return copilot.weekly_summary(db, seller.id)["summary"]
    refund_cmd = re.fullmatch(r"refund\s+#([0-9a-f-]{8,36})(?:\s+(confirm))?", text, re.I)
    if refund_cmd:
        if not refund_cmd[2]:
            return f"Reply refund #{refund_cmd[1][:8]} confirm to issue a full PayPal refund."
        result = copilot.issue_refund(seller.id, refund_cmd[1], confirm=True)
        return (
            f"Refund {result['status']} for #{result['order_id'][:8]} "
            f"({result['amount']} {result['currency']})."
        )
    invoice_cmd = re.fullmatch(
        r"invoice\s+([^\s@<>]+@[^\s@<>]+\.[^\s@<>]+)\s+(\d+(?:\.\d{1,2})?)(?:\s+(.+))?",
        text,
        re.I,
    )
    if invoice_cmd:
        amount_minor = paypal.parse_money(invoice_cmd[2])
        result = copilot.send_invoice(
            seller.id,
            invoice_cmd[1],
            amount_minor,
            invoice_cmd[3] or "Thank you for your order.",
            confirm=True,
        )
        return f"Invoice {result['invoice_id']} sent for {result['amount']} {result['currency']}."
    if text.lower() == "orders":
        rows = db.scalars(
            select(Order)
            .where(Order.seller_id == seller.id)
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        return "Recent orders:\n" + (
            "\n".join(
                f"#{str(r.id)[:8]} {r.status} {paypal.money(r.amount_minor)} {r.currency}"
                for r in rows
            )
            or "No orders yet."
        )
    track = re.fullmatch(
        r"track\s+#([0-9a-f-]{8,36})\s+(\S{1,64})\s+([A-Za-z0-9-]{1,64})", text, re.I
    )
    if track:
        matches = list(
            db.scalars(
                select(Order)
                .where(
                    Order.seller_id == seller.id,
                    cast(Order.id, String).like(track[1].lower() + "%"),
                )
                .limit(2)
            )
        )
        if len(matches) != 1:
            raise DomainError("ORDER_NOT_FOUND", "Use the unique order identifier from orders.")
        body = TrackingInput(carrier=track[2], tracking_number=track[3])
        tracking.track(seller.id, matches[0].id, body.carrier, body.tracking_number)
        return f"Tracking verified for #{str(matches[0].id)[:8]}."
    edit = re.fullmatch(r"(price|stock)\s+(\d+(?:\.\d{1,2})?)(?:\s+#(\d+))?", text, re.I)
    if edit:
        field = edit[1].lower()
        value = (
            paypal.parse_money(edit[2])
            if field == "price"
            else int(edit[2])
            if edit[2].isdigit()
            else -1
        )
        if (
            field == "price"
            and not 1 <= value <= 100_000_000
            or field == "stock"
            and not 0 <= value <= 1_000_000
        ):
            raise DomainError("INVALID_PRODUCT", "Use a positive price or a whole stock quantity.")
        if edit[3]:
            product = db.scalar(
                select(Product)
                .where(
                    Product.seller_id == seller.id,
                    Product.short_no == int(edit[3]),
                    Product.status == "live",
                )
                .with_for_update()
            )
            if not product:
                raise DomainError("PRODUCT_NOT_FOUND", "This live item is unavailable.")
            setattr(product, "price_minor" if field == "price" else "stock", value)
            return f"Item #{product.short_no}: {field} updated."
        if conversation.state != "review":
            return "Wait for a draft, or specify a live item number, for example price 45 #12."
        context["price_minor" if field == "price" else "stock"] = value
        conversation.context = context
        return (
            f"Draft {field} set to {edit[2]}. Set both price and stock, then reply YES to publish."
        )
    remove = re.fullmatch(r"remove\s+#(\d+)", text, re.I)
    if remove:
        product = db.scalar(
            select(Product)
            .where(Product.seller_id == seller.id, Product.short_no == int(remove[1]))
            .with_for_update()
        )
        if not product:
            raise DomainError("PRODUCT_NOT_FOUND", "This item is unavailable.")
        product.status = "archived"
        return f"Item #{product.short_no} archived."
    if text.upper() == "YES" and conversation.state == "review":
        if context.get("price_minor") is None or context.get("stock") is None:
            return "First set your selling price and available stock: price 45, stock 3. Then YES."
        listing = db.get(ListingRequest, uuid.UUID(context["listing_id"]))
        if not listing or listing.seller_id != seller.id:
            raise DomainError("LISTING_NOT_FOUND", "This draft is unavailable.")
        listing_workflow.publish(
            seller.id,
            listing.id,
            listing.draft["title"],
            listing.draft["description"],
            context["price_minor"],
            context["stock"],
        )
        conversation.state, conversation.context = "ready", {}
        return (
            f"Published at {paypal.money(context['price_minor'])} USD. "
            f"Store: {get_settings().frontend_url}/s/{seller.store_slug}."
        )
    return HELP


def draft_reply(db, job):
    phone, listing_id = job.payload["phone"], uuid.UUID(job.payload["listing_id"])
    conversation = db.scalar(
        select(Conversation).where(Conversation.whatsapp_phone == phone).with_for_update()
    )
    listing = db.get(ListingRequest, listing_id)
    seller = db.scalar(
        select(Seller).where(Seller.whatsapp_phone == phone, Seller.status == "active")
    )
    if (
        not listing
        or not seller
        or listing.seller_id != seller.id
        or not conversation
        or conversation.context.get("listing_id") != str(listing_id)
    ):
        return
    if listing.status != "drafted":
        reply(db, job.id, phone, "The draft failed. Use the manual product form in your dashboard.")
        return
    draft = listing.draft
    conversation.state = "review"
    conversation.context = {"listing_id": str(listing_id), "price_minor": None, "stock": None}
    reply(
        db,
        job.id,
        phone,
        f"1. {draft['title']}\n2. {draft['description']}\n"
        f"3. Suggested price only: {paypal.money(draft['suggested_price_minor'])} USD. "
        f"{draft['price_rationale']}\n4. Questions: {'; '.join(draft['questions'])}\n"
        "Set your price and stock, then YES. "
        "To edit title or description, review this draft in the dashboard.",
    )
