from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.mite_public_acquisition import _origin_key, _parse_names


class MitePublicAcquisitionTests(unittest.TestCase):
    def test_origin_key_strips_roboflow_export_suffix(self):
        self.assertEqual(
            _origin_key(Path("leaf_001_jpg.rf.abcdef123456.jpg")),
            "leaf_001_jpg",
        )

    def test_parse_names_from_inline_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.yaml"
            path.write_text(
                "names: ['Adult_female', 'Immature', 'Viable_egg']\n",
                encoding="utf-8",
            )
            self.assertEqual(
                _parse_names(path),
                {0: "Adult_female", 1: "Immature", 2: "Viable_egg"},
            )


if __name__ == "__main__":
    unittest.main()
