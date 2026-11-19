"""Acceptance tests for the v0.1 resource validator CLI."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "language" / "examples"
VALIDATOR = REPO / "language" / "validator" / "validate.py"
SCHEMA_PATH = REPO / "language" / "schema" / "resource.schema.json"
VOCAB_PATH = REPO / "vocabularies" / "core.json"


def run_cli(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def write_doc(directory: Path, document: object) -> Path:
    path = directory / "document.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def assert_valid(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "VALID\n"
    assert result.stderr == ""


def assert_invalid(
    result: subprocess.CompletedProcess[str], *paths: str
) -> None:
    assert result.returncode != 0, result.stdout
    assert result.stdout.startswith("INVALID\n"), result.stdout
    assert result.stderr == ""
    for path in paths:
        assert path in result.stdout, result.stdout


def test_examples_are_valid(tmp_path: Path) -> None:
    names = sorted(path.name for path in EXAMPLES.glob("*.json"))
    # The language milestone shipped three examples. Main later added
    # dataset, service, and error documents; this list has to match the
    # directory or the language CI job fails before it validates them.
    assert names == [
        "article.json",
        "dataset.json",
        "error.json",
        "form.json",
        "product.json",
        "service.json",
    ]
    # Run from a directory that is not the repo root. Schema and vocabulary
    # paths are resolved from the validator file, not from the cwd.
    for name in names:
        result = run_cli(str(EXAMPLES / name), cwd=tmp_path)
        assert_valid(result)


def test_examples_cover_the_three_milestone_types() -> None:
    documents = [load_example(name) for name in ("article.json", "product.json", "form.json")]
    assert {document["type"] for document in documents} == {"article", "form", "product"}


def test_product_purchase_action_is_high_risk() -> None:
    product = load_example("product.json")
    purchase = next(action for action in product["actions"] if action["name"] == "purchase")
    assert purchase["risk"] == "high"
    assert purchase["idempotent"] is False
    result = run_cli(str(EXAMPLES / "product.json"))
    assert_valid(result)


def test_unknown_fields_are_ignored(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["future_extension"] = {"note": "ignored by a v0.1 reader"}
    document["actions"][0]["future_flag"] = True
    document["provenance"]["future_signer_hint"] = "ignored"
    result = run_cli(str(write_doc(tmp_path, document)))
    assert_valid(result)
    assert "future_extension" not in result.stdout
    assert "future_flag" not in result.stdout


def test_empty_actions_and_links_are_valid(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["actions"] = []
    document["links"] = []
    assert_valid(run_cli(str(write_doc(tmp_path, document))))


def test_render_is_optional(tmp_path: Path) -> None:
    document = load_example("form.json")
    del document["render"]
    assert_valid(run_cli(str(write_doc(tmp_path, document))))


def test_missing_required_field(tmp_path: Path) -> None:
    document = load_example("article.json")
    del document["title"]
    assert_invalid(run_cli(str(write_doc(tmp_path, document))), "$.title")


def test_action_missing_required_field(tmp_path: Path) -> None:
    document = load_example("product.json")
    del document["actions"][0]["idempotent"]
    assert_invalid(
        run_cli(str(write_doc(tmp_path, document))),
        "$.actions[0].idempotent",
    )


def test_risk_enum_rejects_bad_value(tmp_path: Path) -> None:
    document = load_example("product.json")
    document["actions"][0]["risk"] = "severe"
    result = run_cli(str(write_doc(tmp_path, document)))
    assert_invalid(result, "$.actions[0].risk")
    assert "severe" in result.stdout


def test_content_missing_required_body(tmp_path: Path) -> None:
    document = load_example("article.json")
    del document["content"]["body"]
    assert_invalid(run_cli(str(write_doc(tmp_path, document))), "$.content.body")


def test_content_rejects_bad_currency(tmp_path: Path) -> None:
    document = load_example("product.json")
    document["content"]["price"]["currency"] = "US"
    assert_invalid(
        run_cli(str(write_doc(tmp_path, document))),
        "$.content.price.currency",
    )


def test_duplicate_action_name(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["actions"].append(copy.deepcopy(document["actions"][0]))
    assert_invalid(run_cli(str(write_doc(tmp_path, document))), "$.actions[1].name")


def test_unknown_resource_type(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["type"] = "page"
    result = run_cli(str(write_doc(tmp_path, document)))
    assert_invalid(result, "$.type")
    assert "core vocabulary" in result.stdout


def test_version_must_be_semver(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["version"] = "0.1"
    assert_invalid(run_cli(str(write_doc(tmp_path, document))), "$.version")


def test_id_must_be_uri(tmp_path: Path) -> None:
    document = load_example("article.json")
    document["id"] = "not a uri"
    assert_invalid(run_cli(str(write_doc(tmp_path, document))), "$.id")


def test_embedded_input_schema_must_be_valid(tmp_path: Path) -> None:
    document = load_example("form.json")
    document["actions"][0]["input_schema"] = {"type": "not-a-type"}
    result = run_cli(str(write_doc(tmp_path, document)))
    assert_invalid(result, "$.actions[0].input_schema")
    assert "not a valid JSON Schema" in result.stdout


def test_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    result = run_cli(str(path))
    assert result.returncode == 1
    assert result.stdout.startswith("INVALID\n")


def test_reports_every_error_path(tmp_path: Path) -> None:
    document = load_example("product.json")
    del document["title"]
    document["actions"][0]["risk"] = "severe"
    assert_invalid(
        run_cli(str(write_doc(tmp_path, document))),
        "$.title",
        "$.actions[0].risk",
    )


def test_usage_error() -> None:
    result = run_cli()
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert result.stdout == ""


def test_schema_is_draft_2020_12_and_forward_compatible() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is True
    assert schema["$defs"]["action"]["additionalProperties"] is True
    assert schema["$defs"]["provenance"]["additionalProperties"] is True
    assert schema["$defs"]["render"]["additionalProperties"] is True
    assert schema["$defs"]["action"]["properties"]["risk"]["enum"] == [
        "low",
        "medium",
        "high",
        "critical",
    ]


def test_core_vocabulary_is_the_existing_six_types() -> None:
    vocabulary = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    assert vocabulary["version"] == "0.1.0"
    assert set(vocabulary["types"]) == {
        "article",
        "product",
        "form",
        "dataset",
        "service",
        "error",
    }
