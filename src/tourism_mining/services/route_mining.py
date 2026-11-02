"""Application service coordinating experiment 3 route processing."""

from pathlib import Path
from typing import Any

from tourism_mining.adapters.route_files import load_documents, write_route_artifacts
from tourism_mining.domain.routes import (
    OFFICIAL_ROUTE_ID,
    TIMED_ROUTE_ID,
    TRAVEL_ROUTE_ID,
    compare_routes,
    parse_annotated_travelogue,
    parse_numbered_timed_route,
    parse_official_chain,
    validate_routes,
)


SOURCE_DOCUMENT_IDS = (OFFICIAL_ROUTE_ID, TIMED_ROUTE_ID, "GG_T01", TRAVEL_ROUTE_ID)


def run_experiment3(input_path: Path, output_dir: Path) -> dict[str, Any]:
    documents = load_documents(input_path)
    missing = [doc_id for doc_id in SOURCE_DOCUMENT_IDS if doc_id not in documents]
    if missing:
        raise ValueError(f"Required source documents are missing: {', '.join(missing)}")

    routes = [
        parse_official_chain(documents[OFFICIAL_ROUTE_ID]),
        parse_numbered_timed_route(documents[TIMED_ROUTE_ID]),
        parse_annotated_travelogue(documents["GG_T01"]),
        parse_annotated_travelogue(documents[TRAVEL_ROUTE_ID]),
    ]
    validate_routes(routes, documents)
    comparison = compare_routes(routes[0], routes[3])
    return write_route_artifacts(
        input_path=input_path,
        output_dir=output_dir,
        source_document_ids=SOURCE_DOCUMENT_IDS,
        documents=documents,
        routes=routes,
        comparison=comparison,
    )
