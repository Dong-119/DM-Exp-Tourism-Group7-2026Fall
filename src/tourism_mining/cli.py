"""Command-line entry point for tourism knowledge-mining experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tourism_mining.config import DEFAULT_EXPERIMENT3_INPUT, DEFAULT_EXPERIMENT3_OUTPUT
from tourism_mining.services.route_mining import run_experiment3


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    experiment3 = commands.add_parser("experiment3", help="Mine and compare route structures")
    experiment3.add_argument("--input", type=Path, default=DEFAULT_EXPERIMENT3_INPUT)
    experiment3.add_argument("--output", type=Path, default=DEFAULT_EXPERIMENT3_OUTPUT)
    args = parser.parse_args(argv)

    manifest = run_experiment3(args.input.resolve(), args.output.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
