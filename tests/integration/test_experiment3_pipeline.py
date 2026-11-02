import json
import tempfile
import unittest
from pathlib import Path

from tourism_mining.config import DEFAULT_EXPERIMENT3_INPUT
from tourism_mining.services.route_mining import run_experiment3


class Experiment3PipelineTests(unittest.TestCase):
    def test_pipeline_writes_reproducible_outputs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            manifest = run_experiment3(DEFAULT_EXPERIMENT3_INPUT, output_dir)

            routes = json.loads((output_dir / "routes.json").read_text(encoding="utf-8"))
            comparison = json.loads(
                (output_dir / "route_comparison.json").read_text(encoding="utf-8")
            )
            saved_manifest = json.loads(
                (output_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            has_steps_csv = (output_dir / "route_steps.csv").is_file()

        self.assertEqual(len(routes), 4)
        self.assertEqual(len(routes[0]["steps"]), 12)
        self.assertEqual(len(routes[2]["time_hierarchy"]["morning"]), 9)
        self.assertEqual(len(routes[2]["time_hierarchy"]["afternoon"]), 4)
        self.assertEqual(comparison["official_route_coverage"], 4 / 12)
        self.assertEqual(comparison["traveler_route_alignment"], 4 / 5)
        self.assertEqual(comparison["shared_order_consistency"], 1.0)
        self.assertEqual(saved_manifest, manifest)
        self.assertTrue(has_steps_csv)


if __name__ == "__main__":
    unittest.main()
