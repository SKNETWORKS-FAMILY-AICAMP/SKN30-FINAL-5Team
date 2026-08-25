from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_runtime_artifacts.py"
spec = importlib.util.spec_from_file_location("build_v2_runtime_artifacts", SCRIPT)
assert spec and spec.loader
runtime_artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_artifacts)


class V2RuntimeArtifactTests(unittest.TestCase):
    def test_materializes_validated_runtime_artifacts_without_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = runtime_artifacts.build(output)

            self.assertEqual(report["representative_records"], 102)
            self.assertEqual(report["alternative_records"], 285)
            self.assertEqual(report["safety_rule_records"], 394)
            self.assertFalse(report["production_eligible"])

            catalog_manifest = json.loads(
                (output / "catalog_manifest.json").read_text(encoding="utf-8")
            )
            alternative_manifest = json.loads(
                (output / "alternatives_manifest.json").read_text(encoding="utf-8")
            )
            safety_manifest = json.loads(
                (output / "safety_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(catalog_manifest["review"]["status"], "DOMAIN_APPROVED")
            self.assertFalse(catalog_manifest["review"]["production_eligible"])
            self.assertEqual(alternative_manifest["summary"]["alternative_records"], 285)
            self.assertEqual(safety_manifest["summary"]["rule_records"], 394)


if __name__ == "__main__":
    unittest.main()
