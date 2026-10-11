"""Evaluation protocol tests with synthetic records; never product-quality results."""

import copy
import io
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

import evaluate_listings as evaluation
from app.errors import DomainError


def fixtures():
    cases = []
    observations = []
    for category in evaluation.CATEGORIES:
        for number in range(5):
            case_id = f"{category}-{number}"
            cases.append(
                {
                    "id": case_id,
                    "category": category,
                    "images": [case_id + ".png"],
                    "expected_attributes": {},
                }
            )
            observations.append(
                {
                    "id": case_id,
                    "elapsed_seconds": 1.0,
                    "error": None,
                    "draft": {
                        "title": "Controlled fixture",
                        "description": "Synthetic test only.",
                        "category": category,
                        "attributes": {},
                        "suggested_price_minor": 100,
                        "price_rationale": "Fixture suggestion",
                        "confidence": 0.8,
                        "questions": [],
                    },
                }
            )
    dataset = evaluation.Dataset(source="team_photographed_products", cases=cases)
    dataset_hash, run_hash = "a" * 64, "b" * 64
    run = evaluation.Run(
        dataset_sha256=dataset_hash,
        model="test-model",
        started_at=datetime.now(UTC),
        image_sha256={case.id: [evaluation.digest(case.id.encode())] for case in dataset.cases},
        observations=observations,
    )
    reviews = evaluation.Reviews(
        run_sha256=run_hash,
        reviewer_id="anonymous-test",
        reviews=[{"id": case.id, "rating": 4, "invented_claim": False} for case in dataset.cases],
    )
    return dataset, dataset_hash, run, run_hash, reviews


def test_complete_protocol_computes_targets_without_gate_approval():
    report = evaluation.score(*fixtures())
    assert report["decision"] == "targets_met"
    assert report["gate_approval"] is False
    assert report["metrics"]["category_correct"] == 20
    assert report["metrics"]["human_rating_average"] == 4
    assert "Controlled fixture" not in json.dumps(report)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "failed", "dataset", "reviews", "image"]
)
def test_incomplete_or_unbound_records_never_pass(mutation):
    dataset, dataset_hash, run, run_hash, reviews = fixtures()
    if mutation == "missing":
        reviews.reviews.pop()
    elif mutation == "duplicate":
        reviews.reviews[-1] = copy.deepcopy(reviews.reviews[0])
    elif mutation == "failed":
        run.observations[-1].draft = None
        run.observations[-1].error = "AI_UNAVAILABLE"
    elif mutation == "dataset":
        run.dataset_sha256 = "c" * 64
    elif mutation == "reviews":
        reviews.run_sha256 = "c" * 64
    else:
        run.image_sha256[dataset.cases[-1].id] = run.image_sha256[dataset.cases[0].id]
    assert (
        evaluation.score(dataset, dataset_hash, run, run_hash, reviews)["decision"] == "incomplete"
    )


def test_p95_uses_nearest_rank_all_twenty_and_strict_boundary():
    args = fixtures()
    run = args[2]
    run.observations[-1].elapsed_seconds = 100
    assert evaluation.score(*args)["metrics"]["draft_p95_seconds"] == 1
    run.observations[-2].elapsed_seconds = 20
    report = evaluation.score(*args)
    assert report["decision"] == "targets_not_met"
    assert report["checks"]["draft_p95_under_20_seconds"] is False


def test_invented_claim_and_low_quality_are_not_hidden():
    args = fixtures()
    args[-1].reviews[0].invented_claim = True
    args[-1].reviews[0].rating = 3
    report = evaluation.score(*args)
    assert report["decision"] == "targets_not_met"
    assert report["metrics"]["invented_claims"] == 1
    assert report["checks"]["human_average_at_least_4_of_5"] is False


def test_category_threshold_exactly_eighteen():
    args = fixtures()
    for item in args[2].observations[:2]:
        item.draft.category = "prints"
    assert evaluation.score(*args)["checks"]["category_at_least_18_of_20"] is True
    args[2].observations[2].draft.category = "prints"
    assert evaluation.score(*args)["checks"]["category_at_least_18_of_20"] is False


def test_dataset_requires_twenty_distinct_balanced_products():
    dataset = fixtures()[0].model_dump()
    for mutate in ["missing", "duplicate", "category"]:
        bad = copy.deepcopy(dataset)
        if mutate == "missing":
            bad["cases"].pop()
        elif mutate == "duplicate":
            bad["cases"][-1]["id"] = bad["cases"][0]["id"]
        else:
            bad["cases"][-1]["category"] = "jewellery"
        with pytest.raises(ValidationError):
            evaluation.Dataset.model_validate(bad)


def test_missing_credentials_do_not_fabricate_a_run(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))
    with pytest.raises(DomainError, match="Configure real Anthropic"):
        evaluation.run_dataset(fixtures()[0], "a" * 64, tmp_path)


def test_preflight_rejects_escape_and_duplicate_photos(tmp_path):
    dataset = fixtures()[0]
    dataset.cases[0].images = ["../private.png"]
    with pytest.raises(ValueError, match="IMAGE_PATH_INVALID"):
        evaluation.prepare_images(dataset, tmp_path)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(data, format="PNG")
    (tmp_path / "same.png").write_bytes(data.getvalue())
    for case in dataset.cases:
        case.images = ["same.png"]
    with pytest.raises(ValueError, match="DUPLICATE_IMAGE"):
        evaluation.prepare_images(dataset, tmp_path)


def test_previous_evidence_is_not_overwritten(tmp_path):
    path = tmp_path / "result.json"
    evaluation.write_json(path, {"decision": "incomplete"})
    with pytest.raises(FileExistsError):
        evaluation.write_json(path, {"decision": "targets_met"})
    assert json.loads(path.read_text())["decision"] == "incomplete"


@pytest.mark.parametrize("rating", [True, None, 0, 6])
def test_human_rating_must_be_explicit_valid_integer(rating):
    with pytest.raises(ValidationError):
        evaluation.Review(id="product-1", rating=rating, invented_claim=False)


def test_cli_binds_files_and_never_prints_draft_content(monkeypatch, tmp_path, capsys):
    dataset, _, run, _, reviews = fixtures()
    dataset_path, run_path = tmp_path / "dataset.json", tmp_path / "run.json"
    review_path, output_path = tmp_path / "reviews.json", tmp_path / "summary.json"
    evaluation.write_json(dataset_path, dataset.model_dump(mode="json"))
    _, dataset_hash = evaluation.read_json(dataset_path)
    run.dataset_sha256 = dataset_hash
    evaluation.write_json(run_path, run.model_dump(mode="json"))
    _, run_hash = evaluation.read_json(run_path)
    reviews.run_sha256 = run_hash
    evaluation.write_json(review_path, reviews.model_dump(mode="json"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_listings.py",
            "score",
            "--dataset",
            str(dataset_path),
            "--run-file",
            str(run_path),
            "--reviews",
            str(review_path),
            "--output",
            str(output_path),
        ],
    )
    assert evaluation.main() == 0
    assert json.loads(output_path.read_text())["decision"] == "targets_met"
    assert "Controlled fixture" not in capsys.readouterr().out
    assert evaluation.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_runner_records_all_twenty_and_redacts_provider_exception(monkeypatch, tmp_path):
    dataset, dataset_hash, *_ = fixtures()
    for number, case in enumerate(dataset.cases):
        data = io.BytesIO()
        Image.new("RGB", (16, 16), (number * 10, 0, 0)).save(data, format="PNG")
        (tmp_path / case.images[0]).write_bytes(data.getvalue())
    monkeypatch.setattr(
        evaluation,
        "get_settings",
        lambda: SimpleNamespace(
            anthropic_api_key="controlled-test-only",
            anthropic_model="test-model",
        ),
    )
    calls = []

    def fail(images, caption):
        calls.append(len(images))
        raise RuntimeError("private-provider-secret")

    monkeypatch.setattr(evaluation.llm, "draft_listing", fail)
    run = evaluation.run_dataset(dataset, dataset_hash, tmp_path)
    assert len(calls) == len(run.observations) == 20
    assert all(item.error == "EVAL_CASE_FAILED" for item in run.observations)
    assert "private-provider-secret" not in run.model_dump_json()
