"""Default repository paths used by local experiment commands."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROCESSED_DATA = REPOSITORY_ROOT / "data" / "processed"
DEFAULT_EXPERIMENT3_INPUT = DEFAULT_PROCESSED_DATA / "clean_documents.json"
DEFAULT_EXPERIMENT3_OUTPUT = DEFAULT_PROCESSED_DATA / "experiment3"
