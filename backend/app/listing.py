"""Listing schema and safe image preprocessing; publishing needs seller confirmation."""

import io
import warnings
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from app.errors import DomainError
from app.guards import safe_text


class Attributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str | None = Field(default=None, max_length=80)
    colour: str | None = Field(default=None, max_length=80)
    size_hint: str | None = Field(default=None, max_length=80)
    handmade: bool | None = None


class ListingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=600)
    category: Literal["jewellery", "textiles", "crafts", "prints"]
    attributes: Attributes
    suggested_price_minor: int = Field(gt=0, le=1000000, strict=True)
    price_rationale: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    questions: list[str] = Field(max_length=10)


def validate_draft(draft):
    """Validate model output and reject instructions before seller review."""
    result = ListingDraft.model_validate(draft)
    for text in [
        result.title,
        result.description,
        result.price_rationale,
        *result.questions,
        result.attributes.material or "",
        result.attributes.colour or "",
        result.attributes.size_hint or "",
    ]:
        safe_text(text)
    if any(len(question) > 200 for question in result.questions):
        raise DomainError("INVALID_DRAFT", "Listing questions are too long.")
    return result


def preprocess_image(raw: bytes):
    """Decode allowed image content, remove metadata and bound pixel/resource use."""
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise DomainError("INVALID_IMAGE", "Use a JPEG, PNG or WebP image no larger than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if (
                    image.format not in {"JPEG", "PNG", "WEBP"}
                    or image.width * image.height > 16000000
                ):
                    raise DomainError("INVALID_IMAGE", "Use a supported image under 16 megapixels.")
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((1024, 1024))
                clean = Image.new("RGB", image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise DomainError("INVALID_IMAGE", "The image cannot be decoded safely.") from exc
