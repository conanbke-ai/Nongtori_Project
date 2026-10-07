from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.development_cv_v1 import build_weight_train_cv_manifest


class WeightDevelopmentCvV1Test(unittest.TestCase):
    def _write_split(self, path: Path, *, train: int, validation: int, test: int) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["fruit_id", "split"])
            writer.writeheader()
            index = 0
            for split, count in (
                ("train", train),
                ("validation", validation),
                ("test", test),
            ):
                for _ in range(count):
                    writer.writerow(
                        {
                            "fruit_id": f"{index:04d}",
                            "split": split,
                        }
                    )
                    index += 1

    def test_367_train_fruits_make_balanced_five_folds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split_csv = root / "fruit-splits.csv"
            self._write_split(split_csv, train=367, validation=79, test=78)

            report = build_weight_train_cv_manifest(
                split_csv,
                root / "cv",
                folds=5,
                seed="fixed",
            )

            self.assertEqual(report["development_pool_count"], 367)
            self.assertEqual(
                sorted(report["fold_counts"].values(), reverse=True),
                [74, 74, 73, 73, 73],
            )
            self.assertEqual(
                report["official_split_counts"],
                {"train": 367, "validation": 79, "test": 78},
            )

    def test_manifest_contains_only_official_train_fruits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split_csv = root / "fruit-splits.csv"
            self._write_split(split_csv, train=10, validation=3, test=2)

            report = build_weight_train_cv_manifest(
                split_csv,
                root / "cv",
                folds=5,
                seed="fixed",
            )

            manifest = Path(report["manifest"])
            with manifest.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 10)
            self.assertEqual({row["official_split"] for row in rows}, {"train"})
            self.assertEqual(
                report["leakage_guards"],
                {
                    "official_validation_in_cv": False,
                    "official_test_in_cv": False,
                    "same_fruit_cross_cv_fold": False,
                },
            )

    def test_assignment_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split_csv = root / "fruit-splits.csv"
            self._write_split(split_csv, train=20, validation=5, test=5)

            first = build_weight_train_cv_manifest(
                split_csv,
                root / "a",
                folds=5,
                seed="same-seed",
            )
            second = build_weight_train_cv_manifest(
                split_csv,
                root / "b",
                folds=5,
                seed="same-seed",
            )

            self.assertEqual(
                Path(first["manifest"]).read_text(encoding="utf-8"),
                Path(second["manifest"]).read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
