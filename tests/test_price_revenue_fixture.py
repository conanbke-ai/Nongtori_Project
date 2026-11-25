"""Check synthetic harvest/worker payloads and independent revenue expectations."""

import json
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ml.price_forecast.incremental_planner import KST, Series


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "price_revenue_synthetic.json"


class RevenueFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_completion_claim_and_result_reference_the_same_harvest(self):
        harvest = self.scenario["harvest"]
        claim = self.scenario["claim"]
        job = claim["job"]
        result = self.scenario["worker_result"]
        self.assertEqual(
            (harvest["runId"], harvest["farmId"], harvest["itemId"]),
            (job["harvest_run_id"], job["farm_id"], job["item_id"]),
        )
        completed_at = datetime.fromisoformat(job["completed_at"])
        self.assertEqual(datetime.fromisoformat(harvest["completedAt"]), completed_at)
        self.assertLess(datetime.fromisoformat(harvest["startedAt"]), completed_at)
        self.assertEqual((result["jobId"], result["harvestRunId"]), (job["id"], job["harvest_run_id"]))
        self.assertIn(
            (result["modelName"], result["modelVersion"]),
            {(model["model_name"], model["model_version"]) for model in claim["activeModels"]},
        )
        self.assertEqual(claim["grades"], [
            {"grade_code": row["gradeCode"], "fruit_count": row["fruitCount"], "total_weight_g": row["totalWeightG"]}
            for row in harvest["grades"]
        ])
        self.assertEqual(job["harvested_count"], sum(row["fruit_count"] for row in claim["grades"]))
        self.assertEqual(job["total_weight_g"], sum(row["total_weight_g"] for row in claim["grades"]))
        harvest_day = completed_at.astimezone(KST).date()
        self.assertEqual((date.fromisoformat(result["targetDate"]) - harvest_day).days, result["horizonDays"])

    def test_each_sale_channel_has_a_distinct_exact_grade_price(self):
        claim = self.scenario["claim"]
        channels = self.scenario["sale_channels"]
        self.assertEqual(self.scenario["fixture_kind"], "SYNTHETIC")
        self.assertEqual(self.scenario["usage_assignment"], "SYNTHETIC_SCENARIO_DECISION")
        self.assertCountEqual((channel["usage"] for channel in channels), ["FRESH", "PROCESSING_JAM"])
        grades = [row["grade_code"] for row in claim["grades"]]
        self.assertCountEqual((channel["harvest_grade_code"] for channel in channels), grades)
        predictions = self.scenario["worker_result"]["predictions"]
        self.assertCountEqual((prediction["gradeCode"] for prediction in predictions), grades)
        self.assertEqual(len(set(grades)), len(grades))
        series = [Series(**channel["price_series"]) for channel in channels]
        self.assertEqual(len(set(series)), len(channels))
        for price_series in series:
            self.assertTrue(price_series.provider.startswith("synthetic-"))
            self.assertEqual((price_series.product, price_series.cultivar),
                             (claim["job"]["crop_code"], claim["job"]["cultivar_code"]))
        for prediction in predictions:
            self.assertLessEqual(0, prediction["p10"])
            self.assertLessEqual(prediction["p10"], prediction["p50"])
            self.assertLessEqual(prediction["p50"], prediction["p90"])

    def test_grade_specific_krw_per_kg_yields_gross_scenarios(self):
        self.assertEqual((self.scenario["harvest_weight_unit"], self.scenario["price_unit"]), ("g", "KRW/kg"))
        weights_kg = {
            grade["grade_code"]: Decimal(grade["total_weight_g"]) / 1000
            for grade in self.scenario["claim"]["grades"]
        }
        usage_by_grade = {
            channel["harvest_grade_code"]: channel["usage"] for channel in self.scenario["sale_channels"]
        }
        predictions = self.scenario["worker_result"]["predictions"]
        gross_by_usage = {
            usage_by_grade[row["gradeCode"]]: weights_kg[row["gradeCode"]] * row["p50"]
            for row in predictions
        }
        expected = self.scenario["expected"]
        self.assertEqual(gross_by_usage["FRESH"], expected["expected_fresh_gross_won"])
        self.assertEqual(gross_by_usage["PROCESSING_JAM"], expected["expected_processing_jam_gross_won"])
        self.assertEqual(sum(gross_by_usage.values()), expected["estimated_gross_won"])
        self.assertEqual(sum(weights_kg[row["gradeCode"]] * row["p10"] for row in predictions),
                         expected["gross_scenario_low_won"])
        self.assertEqual(sum(weights_kg[row["gradeCode"]] * row["p90"] for row in predictions),
                         expected["gross_scenario_high_won"])
        self.assertEqual(expected["range_interpretation"], "MATCHED_GRADE_PRICE_SCENARIOS")
        self.assertEqual(expected["worker_status_without_cost_settings"], "PRICE_ONLY")
        self.assertIsNone(expected["actual_settlement_won"])


if __name__ == "__main__":
    unittest.main()
