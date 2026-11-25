"""Synthetic adapter-to-baseline fixtures. No provider data or network."""

import hashlib
import io
import json
import unittest
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

from ml.price_forecast.at_auction import PROVIDER, AuctionEdition, AuctionQuery, AuctionRejection, AuctionTrade
from ml.price_forecast.auction_history import (
    WithdrawalEvidence,
    reconcile_auction_editions,
    summarize_population,
    write_daily_prices,
)
from ml.price_forecast.baseline import load_daily_prices
from ml.price_forecast.incremental_planner import KST, Series


TRADE_DAY = date(2026, 1, 1)
QUERY = AuctionQuery(date(2026, 1, 2), "001", "0007", "012")
SERIES = Series(PROVIDER, QUERY.market, QUERY.corporation, "001:012", "004", "007", "02", "12:1:1:2")


def captured(day):
    return datetime(2026, 1, day, 10, tzinfo=KST)


def trade(suffix, amount, mass, *, series=SERIES):
    return AuctionTrade(("SYNTHETIC", suffix), series, TRADE_DAY, Decimal(amount), Decimal(mass))


def edition(day, digest, *trades, query=QUERY, duplicates=0, rejections=()):
    return AuctionEdition(
        query, captured(day), digest * 64, (), trades, len(trades) + duplicates + len(rejections),
        duplicates, rejections,
    )


class AuctionHistoryTests(unittest.TestCase):
    def test_weighted_price_and_correction_replay_with_immutable_provenance(self):
        first = trade("01", "4000", "2")
        second = trade("02", "21000", "3")
        changed = replace(first, total_krw=Decimal("9000"))
        original = edition(2, "a", first, second, duplicates=1)
        repeat = replace(original, available_at=captured(3))
        corrected = edition(4, "b", changed, second)
        history = reconcile_auction_editions((corrected, original, original, repeat))
        self.assertEqual(history.counts["supplied_editions"], 4)
        self.assertEqual(history.counts["validated_editions"], 3)
        self.assertEqual(history.counts["duplicate_rows"], 2)
        self.assertEqual(history.counts["corrected_trades"], 1)
        earlier, later = history.prices
        self.assertEqual(
            [(row.available_at, row.price_krw_per_kg, row.trade_volume_kg) for row in (earlier, later)],
            [(captured(2), 5000, 5), (captured(4), 6000, 5)],
        )
        entry = history.manifest[later.source_sha256]
        self.assertEqual(entry["active_source_sha256"], ["a" * 64, "b" * 64])
        self.assertEqual(entry["previous_source_sha256"], ["a" * 64])
        serialized = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.assertEqual(later.source_sha256, hashlib.sha256(serialized).hexdigest())
        output = io.StringIO()
        write_daily_prices(output, history.prices)
        output.seek(0)
        self.assertEqual(load_daily_prices(output), list(history.prices))

    def test_scope_preserves_actual_trade_day_and_combines_multiple_settlement_days(self):
        other_scope = replace(QUERY, settlement_day=date(2026, 1, 3))
        first = edition(3, "a", trade("01", "4000", "2"))
        second = edition(3, "b", trade("02", "21000", "3"), query=other_scope)
        result = reconcile_auction_editions((second, first))
        self.assertEqual(len(result.prices), 1)
        daily = result.prices[0]
        self.assertEqual((daily.trade_day, daily.available_at, daily.trade_volume_kg), (TRADE_DAY, captured(3), 5))
        self.assertEqual(daily.price_krw_per_kg, 5000)
        self.assertEqual(result.manifest[daily.source_sha256]["change_source_sha256"], ["a" * 64, "b" * 64])

    def test_scope_overlap_and_cross_scope_identity_collision_block_export(self):
        row = trade("01", "4000", "2")
        original = edition(2, "a", row)
        overlapping = edition(3, "b", query=replace(QUERY, corporation=None))
        collision = edition(3, "b", row, query=replace(QUERY, settlement_day=date(2026, 1, 3)))
        with self.assertRaisesRegex(ValueError, "Overlapping acquisition scopes"):
            reconcile_auction_editions((original, overlapping))
        with self.assertRaisesRegex(ValueError, "multiple acquisition scopes"):
            reconcile_auction_editions((original, collision))

    def test_confirmed_withdrawal_and_reappearance_have_independent_clocks(self):
        row = trade("01", "4000", "2")
        original, absent, reinstated = edition(2, "a", row), edition(3, "b"), edition(4, "a", row)
        proof = WithdrawalEvidence(QUERY, absent.source_sha256, row.trade_id, captured(3), "e" * 64)
        for confirmations in ((), (replace(proof, observed_at=captured(1)),)):
            with self.assertRaisesRegex(ValueError, "Unconfirmed disappearance"):
                reconcile_auction_editions((original, absent), withdrawals=confirmations)
        with self.assertRaisesRegex(ValueError, "independent"):
            reconcile_auction_editions((original, absent), withdrawals=(replace(proof, source_sha256="b" * 64),))
        history = reconcile_auction_editions((original, absent, reinstated), withdrawals=(proof,))
        self.assertEqual(history.counts["withdrawn_trades"], 1)
        self.assertEqual([row.price_krw_per_kg for row in history.prices], [2000, None, 2000])
        tombstone = history.prices[1]
        self.assertEqual(tombstone.available_at, captured(3))
        self.assertEqual(history.manifest[tombstone.source_sha256]["withdrawal_evidence_sha256"], ["e" * 64])

    def test_delayed_withdrawal_proof_does_not_backdate_or_reorder_captures(self):
        row = trade("01", "4000", "2")
        first = edition(2, "a", row)
        absent = edition(3, "b")
        proof = WithdrawalEvidence(QUERY, absent.source_sha256, row.trade_id, captured(5), "e" * 64, captured(3))
        result = reconcile_auction_editions((first, absent), withdrawals=(proof,))
        final = result.prices[-1]
        self.assertEqual((final.available_at, final.price_krw_per_kg), (captured(5), None))
        self.assertEqual(result.manifest[final.source_sha256]["change_source_captures"], [
            {"source_sha256": "b" * 64, "captured_at": "2026-01-03T01:00:00+00:00"}
        ])
        reinstated = edition(4, "c", replace(row, total_krw=Decimal("5000")))
        result = reconcile_auction_editions((reinstated, absent, first), withdrawals=(proof,))
        self.assertEqual(
            [(price.available_at, price.price_krw_per_kg) for price in result.prices],
            [(captured(2), 2000), (captured(5), 2500)],
        )

    def test_corrected_series_retracts_only_old_group(self):
        first = trade("01", "4000", "2")
        changed = replace(first, series=replace(SERIES, grade="05", origin="099"), total_krw=Decimal("5000"))
        result = reconcile_auction_editions((edition(2, "a", first), edition(3, "b", changed)))
        self.assertEqual([
            (row.series.origin, row.series.grade, row.price_krw_per_kg, row.available_at) for row in result.prices
        ], [("004", "02", 2000, captured(2)), ("004", "02", None, captured(3)), ("099", "05", 2500, captured(3))])

    def test_safe_non_auction_exclusion_and_ambiguous_partial_admission(self):
        expected = AuctionRejection(1, 1, "NON_AUCTION_TRADE_TYPE")
        held = AuctionRejection(1, 2, "MISSING_OR_INVALID_TRADE_TIME")
        known = reconcile_auction_editions((edition(2, "a", rejections=(expected,)),))
        self.assertEqual((known.counts["excluded_non_auction_rows"], known.prices), (1, ()))
        with self.assertRaisesRegex(ValueError, "MISSING_OR_INVALID_TRADE_TIME=1"):
            reconcile_auction_editions((edition(2, "b", rejections=(expected, held)),))

    def test_population_preserves_exact_cultivar_and_series_keys(self):
        first = trade("01", "4000", "2")
        other_origin = trade("02", "4000", "2", series=replace(SERIES, origin="014"))
        other_cultivar = trade("03", "4000", "2", series=replace(SERIES, cultivar="07"))
        result = reconcile_auction_editions((edition(2, "a", first, other_origin, other_cultivar),))
        coverage = summarize_population(result, cultivar="007", product="001:012")
        self.assertEqual(coverage["excluded_other_cultivar_versions"], 1)
        self.assertEqual(coverage["availability_basis"], "COMPLETE_RESPONSE_CAPTURE_AND_REQUIRED_WITHDRAWAL_EVIDENCE")
        self.assertEqual([r["series"]["origin"] for r in coverage["series"]], ["004", "014"])
        self.assertTrue(all(r["first_available_at"] == "2026-01-02T01:00:00+00:00" for r in coverage["series"]))

    def test_category_and_cultivar_filters_bound_the_scope(self):
        exact = replace(QUERY, category="001", cultivar="007")
        other = replace(exact, cultivar="008")
        first = trade("01", "4000", "2")
        second = trade("02", "4000", "2", series=replace(SERIES, cultivar="008"))
        result = reconcile_auction_editions((edition(2, "a", first, query=exact), edition(2, "b", second, query=other)))
        self.assertEqual(len(result.prices), 2)
        for wrong_scope in (other, replace(exact, category="002")):
            with self.subTest(wrong_scope=wrong_scope), self.assertRaisesRegex(ValueError, "invalid trade"):
                reconcile_auction_editions((edition(2, "a", first, query=wrong_scope),))
        with self.assertRaisesRegex(ValueError, "Overlapping acquisition scopes"):
            reconcile_auction_editions((edition(2, "a", first, query=exact), edition(2, "b", second)))

    def test_conflicting_simultaneous_editions_and_unused_confirmation_are_rejected(self):
        row = trade("01", "4000", "2")
        first = edition(2, "a", row)
        conflicting = edition(2, "b", row)
        with self.assertRaisesRegex(ValueError, "Conflicting editions"):
            reconcile_auction_editions((first, conflicting))
        evidence = WithdrawalEvidence(QUERY, first.source_sha256, row.trade_id, captured(2), "e" * 64)
        with self.assertRaisesRegex(ValueError, "does not match"):
            reconcile_auction_editions((first,), withdrawals=(evidence,))


if __name__ == "__main__":
    unittest.main()
