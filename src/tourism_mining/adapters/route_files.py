"""JSON and CSV storage adapters for route-mining artifacts."""

import csv
import json
from pathlib import Path
from typing import Any


def load_documents(path: Path) -> dict[str, dict[str, Any]]:
    documents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(documents, list):
        raise ValueError(f"Expected a JSON array in {path}")

    by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError(f"Expected document objects in {path}")
        doc_id = document.get("doc_id")
        if not doc_id or doc_id in by_id:
            raise ValueError(f"Missing or duplicate doc_id: {doc_id!r}")
        if not isinstance(document.get("clean_content"), str):
            raise ValueError(f"Missing clean_content for {doc_id}")
        by_id[doc_id] = document
    return by_id


def write_route_artifacts(
    input_path: Path,
    output_dir: Path,
    source_document_ids: tuple[str, ...],
    documents: dict[str, dict[str, Any]],
    routes: list[dict[str, Any]],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "routes.json", routes)
    _write_json(output_dir / "route_comparison.json", comparison)
    _write_steps_csv(output_dir / "route_steps.csv", routes)

    try:
        input_location = str(input_path.resolve().relative_to(_repository_root()))
    except ValueError:
        input_location = str(input_path.resolve())

    manifest = {
        "experiment": "3",
        "input": input_location,
        "source_documents": [
            {
                "doc_id": doc_id,
                "clean_sha256": documents[doc_id].get("clean_sha256"),
                "provenance_kind": documents[doc_id].get("provenance_kind"),
            }
            for doc_id in source_document_ids
        ],
        "outputs": ["routes.json", "route_steps.csv", "route_comparison.json"],
        "route_count": len(routes),
        "official_route_step_count": len(routes[0]["steps"]),
        "time_layered_traveler_route_step_count": len(routes[2]["steps"]),
        "comparison_traveler_route_step_count": len(routes[3]["steps"]),
        "comparison": comparison,
        "validation": "passed",
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    return manifest


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_steps_csv(path: Path, routes: list[dict[str, Any]]) -> None:
    fields = (
        "route_id", "route_kind", "provenance_kind", "document_id", "scenic_name",
        "order", "poi", "poi_kind", "raw_label", "activity", "step_type", "time_slot",
        "time_start", "time_end", "time_source", "source_quote", "source_span",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for route in routes:
            for step in route["steps"]:
                writer.writerow({
                    "route_id": route["route_id"],
                    "route_kind": route["route_kind"],
                    "provenance_kind": route["provenance_kind"],
                    "document_id": route["document_id"],
                    "scenic_name": route["scenic_name"],
                    **{field: step[field] for field in fields[5:-1]},
                    "source_span": json.dumps(step["source_span"], ensure_ascii=False),
                })


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]
