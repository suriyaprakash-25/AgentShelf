"""Run and score the roadmap's real-photo listing evaluation; never invent ratings."""

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app import llm
from app.config import get_settings
from app.errors import DomainError
from app.listing import Attributes, ListingDraft, preprocess_image
from app.listing_workflow import caption_text

CATEGORIES = ("jewellery", "textiles", "crafts", "prints")
CaseId = str


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProductCase(Input):
    id: CaseId = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    category: Literal["jewellery", "textiles", "crafts", "prints"]
    images: list[str] = Field(min_length=1, max_length=4)
    caption: str = Field(default="", max_length=600)
    expected_attributes: Attributes


class Dataset(Input):
    source: Literal["team_photographed_products"]
    cases: list[ProductCase] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def complete(self):
        if len({case.id for case in self.cases}) != 20 or Counter(
            case.category for case in self.cases
        ) != Counter(dict.fromkeys(CATEGORIES, 5)):
            raise ValueError("DATASET_COVERAGE_INVALID")
        return self


class Observation(Input):
    id: CaseId = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    elapsed_seconds: float = Field(ge=0, strict=True, allow_inf_nan=False)
    draft: ListingDraft | None
    error: Literal["AI_UNAVAILABLE", "AI_INVALID_DRAFT", "EVAL_CASE_FAILED"] | None

    @model_validator(mode="after")
    def outcome(self):
        if (self.draft is None) == (self.error is None):
            raise ValueError("OUTCOME_INVALID")
        return self


class Run(Input):
    version: Literal[1] = 1
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: Literal["anthropic", "gemini"] = "anthropic"
    model: str = Field(pattern=r"^[a-zA-Z0-9._:/-]{1,120}$")
    started_at: datetime
    image_sha256: dict[str, list[str]]
    observations: list[Observation] = Field(max_length=20)


class Review(Input):
    id: CaseId = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    rating: int = Field(ge=1, le=5, strict=True)
    invented_claim: bool = Field(strict=True)


class Reviews(Input):
    run_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    reviews: list[Review] = Field(max_length=20)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path, max_bytes=1024 * 1024):
    with Path(path).open("rb") as source:
        raw = source.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("EVAL_INPUT_TOO_LARGE")
    return json.loads(raw), digest(raw)


def write_json(path, data):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Preserve previous runs and human reviews instead of silently replacing evidence.
    with destination.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2, allow_nan=False)
        output.write("\n")


def prepare_images(dataset, directory):
    """Validate all 20 products before any paid model call; bind de-identified images."""
    root = Path(directory).resolve()
    prepared, fingerprints, seen = {}, {}, set()
    for case in dataset.cases:
        caption_text(case.caption)
        prepared[case.id], fingerprints[case.id] = [], []
        for filename in case.images:
            path = (root / filename).resolve()
            if Path(filename).is_absolute() or not path.is_relative_to(root):
                raise ValueError("IMAGE_PATH_INVALID")
            with path.open("rb") as image:
                raw = image.read(5 * 1024 * 1024 + 1)
            clean = preprocess_image(raw)
            fingerprint = digest(clean)
            if fingerprint in seen:
                raise ValueError("DUPLICATE_IMAGE")
            seen.add(fingerprint)
            prepared[case.id].append(clean)
            fingerprints[case.id].append(fingerprint)
    return prepared, fingerprints


def run_dataset(dataset, dataset_hash, directory):
    settings = get_settings()
    if not llm.ai_configured(settings):
        raise DomainError("AI_NOT_CONFIGURED", "Configure real AI access to evaluate.", 503)
    use_gemini = bool(settings.gemini_api_key and not settings.anthropic_api_key)
    active_model = settings.gemini_model if use_gemini else settings.anthropic_model
    if not re.fullmatch(r"[a-zA-Z0-9._:/-]{1,120}", active_model):
        raise ValueError("MODEL_INVALID")
    images, fingerprints = prepare_images(dataset, directory)
    observations = []
    started_at = datetime.now(UTC)
    for case in dataset.cases:
        started = time.monotonic()
        draft, error = None, None
        try:
            draft = llm.draft_listing(images[case.id], caption_text(case.caption))
        except DomainError as exc:
            error = (
                exc.code
                if exc.code in {"AI_UNAVAILABLE", "AI_INVALID_DRAFT"}
                else "EVAL_CASE_FAILED"
            )
        except Exception:
            error = "EVAL_CASE_FAILED"
        observations.append(
            Observation(
                id=case.id,
                elapsed_seconds=time.monotonic() - started,
                draft=draft,
                error=error,
            )
        )
    return Run(
        dataset_sha256=dataset_hash,
        provider="gemini" if use_gemini else "anthropic",
        model=active_model,
        started_at=started_at,
        image_sha256=fingerprints,
        observations=observations,
    )


def score(dataset, dataset_hash, run, run_hash, reviews, second_reviews=None):
    """Calculate targets from complete, bound records; missing evidence never passes."""
    report = {
        "evaluation": "listing_quality_and_draft_latency",
        "decision": "incomplete",
        "gate_approval": False,
        "dataset_sha256": dataset_hash,
        "run_sha256": run_hash,
        "latency_scope": "Local provider/schema call; excludes hosted queue, storage and upload",
        "staging_latency_verified": False,
        "evidence_boundary": (
            "Owner-supplied photographs and human ratings; independent review required"
        ),
    }
    if second_reviews is None or reviews.reviewer_id == second_reviews.reviewer_id:
        return report
    panels = (reviews, second_reviews)
    ids = {case.id for case in dataset.cases}
    outputs = {item.id: item for item in run.observations}
    ratings = [{item.id: item for item in panel.reviews} for panel in panels]
    hashes_valid = set(run.image_sha256) == ids and all(
        len(run.image_sha256[case.id]) == len(case.images)
        and all(re.fullmatch(r"[a-f0-9]{64}", value) for value in run.image_sha256[case.id])
        for case in dataset.cases
    )
    all_hashes = [value for values in run.image_sha256.values() for value in values]
    if (
        run.dataset_sha256 != dataset_hash
        or any(panel.run_sha256 != run_hash for panel in panels)
        or len(outputs) != len(run.observations)
        or any(
            len(records) != len(panel.reviews)
            for records, panel in zip(ratings, panels, strict=True)
        )
        or set(outputs) != ids
        or any(set(records) != ids for records in ratings)
        or not hashes_valid
        or len(set(all_hashes)) != len(all_hashes)
        or any(item.draft is None or item.error is not None for item in outputs.values())
    ):
        return report
    correct = sum(outputs[case.id].draft.category == case.category for case in dataset.cases)
    rating_sum = sum(item.rating for records in ratings for item in records.values())
    invented = sum(any(records[case_id].invented_claim for records in ratings) for case_id in ids)
    # Nearest-rank p95 of all twenty observations, never successful/fast subsets.
    p95 = sorted(item.elapsed_seconds for item in outputs.values())[math.ceil(0.95 * 20) - 1]
    checks = {
        "category_at_least_18_of_20": correct >= 18,
        "human_average_at_least_4_of_5": rating_sum >= 160,
        "zero_invented_claims": invented == 0,
        "draft_p95_under_20_seconds": p95 < 20,
    }
    report.update(
        model=run.model,
        decision="targets_met" if all(checks.values()) else "targets_not_met",
        metrics={
            "products": 20,
            "category_correct": correct,
            "human_reviews": 40,
            "human_rating_average": rating_sum / 40,
            "invented_claims": invented,
            "draft_p95_seconds": p95,
        },
        checks=checks,
        reviewer_summaries=[
            {
                "reviewer_id": panel.reviewer_id,
                "human_rating_average": sum(item.rating for item in panel.reviews) / 20,
                "reviews_sha256": digest(
                    json.dumps(panel.model_dump(mode="json"), sort_keys=True).encode()
                ),
            }
            for panel in panels
        ],
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "score"])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-file")
    parser.add_argument(
        "--reviews", action="append", help="Repeat for each of two human review files"
    )
    args = parser.parse_args()
    try:
        if Path(args.output).exists():
            raise FileExistsError("EVAL_OUTPUT_EXISTS")
        data, dataset_hash = read_json(args.dataset)
        dataset = Dataset.model_validate(data)
        if args.action == "run":
            run = run_dataset(dataset, dataset_hash, Path(args.dataset).parent)
            write_json(args.output, run.model_dump(mode="json"))
            _, run_hash = read_json(args.output)
            print(json.dumps({"status": "recorded", "run_sha256": run_hash}))
            return 0 if all(item.draft is not None for item in run.observations) else 1
        if not args.run_file or not args.reviews or len(args.reviews) != 2:
            raise ValueError("EVAL_INPUT_INVALID")
        run_data, run_hash = read_json(args.run_file)
        review_data = [read_json(path)[0] for path in args.reviews]
        report = score(
            dataset,
            dataset_hash,
            Run.model_validate(run_data),
            run_hash,
            *(Reviews.model_validate(data) for data in review_data),
        )
        write_json(args.output, report)
        print(json.dumps({"decision": report["decision"], "gate_approval": False}))
        return 0 if report["decision"] == "targets_met" else 1
    except (ValidationError, ValueError, OSError, DomainError, RecursionError):
        # Never echo invalid captions, filenames, keys, draft content or provider errors.
        print(json.dumps({"status": "failed", "code": "EVAL_INPUT_OR_PROVIDER_NOT_READY"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
