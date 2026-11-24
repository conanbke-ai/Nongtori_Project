import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from ml.price_forecast.incremental_planner import (
    Acquisition, Observation, Receipt, Series, Target, plan_updates,
)


DAY0, DAY1, DAY2 = (date(2026, 1, day) for day in (1, 2, 3))
BEFORE, FIRST, NOW, FUTURE = (
    datetime(2026, 1, day, tzinfo=timezone.utc) for day in (1, 2, 3, 4)
)
A = Series("provider", "market", "00001101", "01", "origin-a", "cv", "grade", "kg")
B = replace(A, origin="origin-b")
R1 = Acquisition("provider", "settled/v1", "market", DAY1, frozenset({"origin"}), "00001101", "01")
R2 = replace(R1, settlement_day=DAY2)


def source(request, rows=(), *, digest="a", complete=True, available=FIRST):
    return Receipt(request, digest * 64, complete, available,
                   tuple(replace(row, source_sha256=digest * 64) for row in rows))


def run(targets, receipts=(), models=()):
    return plan_updates(tuple(targets), tuple(receipts), frozenset(models), as_of=NOW)


def target(series=A, requests=(R1,), minimum=1):
    return Target(requests, series, True, BEFORE, minimum)


class IncrementalPlanTests(unittest.TestCase):
    def test_overlapping_origins_share_only_the_input(self):
        targets = (target(A), target(B))
        self.assertEqual(run(targets).fetch, (R1,))
        saved = source(R1, [Observation(A, DAY1, FIRST, "a" * 64), Observation(B, DAY1, None, "a" * 64)])
        result = run(targets, [saved], [A])
        self.assertEqual(result.fetch, ())
        self.assertEqual([(d.series.origin, d.state, d.new_days) for d in result.decisions], [
            ("origin-a", "RETRAIN_CANDIDATE", 1),
            ("origin-b", "NO_APPROVED_MODEL", 0),
        ])

    def test_request_identity_dimensions(self):
        variants = [R2, replace(R1, endpoint="settled/v2"), replace(R1, corporation_filter=None),
                    replace(R1, product_filter=None), replace(R1, fields=frozenset({"origin", "weight"}))]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(run([target(requests=(variant,))], [source(R1)]).fetch, (variant,))
        self.assertEqual(R1.corporation_filter, "00001101")
        self.assertEqual(R1.product_filter, "01")
        with self.assertRaises(ValueError):
            replace(R1, product_filter=1)

    def test_unconfirmed_sources_never_queue(self):
        result = run([replace(target(), source_and_units_confirmed=False)])
        self.assertEqual((result.fetch, result.decisions[0].state), ((), "UNVERIFIED_SOURCE"))

    def test_incomplete_unverified_or_future_receipt_is_never_used(self):
        for item in (source(R1, complete=False), source(R1, digest="z"),
                     source(R1, available=None), source(R1, available=FUTURE)):
            self.assertEqual(run([target()], [item]).fetch, (R1,))

    def test_ambiguous_editions_never_train(self):
        result = run([target()], [source(R1), source(R1, digest="b")], [A])
        self.assertEqual((result.fetch, result.decisions[0].state), ((), "AMBIGUOUS_ACQUISITION"))

    def test_same_digest_conflicting_metadata_fails_closed(self):
        with self.assertRaises(ValueError):
            run([target()], [source(R1), source(R1, [Observation(A, DAY1, FIRST, "a" * 64)])])

    def test_unique_trade_days_aggregate_across_settlement_dates(self):
        spill = Observation(A, DAY0, FIRST, "a" * 64)
        current = Observation(A, DAY2, NOW, "a" * 64)
        result = run([target(requests=(R1, R2), minimum=2)], [source(R1, [spill]), source(R2, [spill, current], available=NOW)])
        self.assertEqual((result.decisions[0].state, result.decisions[0].new_days), ("RETRAIN_CANDIDATE", 2))

    def test_missing_date_blocks_partial_retraining(self):
        result = run([target(requests=(R1, R2))], [source(R1, [Observation(A, DAY1, FIRST, "a" * 64)])], [A])
        self.assertEqual((result.fetch, result.decisions[0].state), ((R2,), "AWAITING_ACQUISITION"))

    def test_unavailable_and_already_counted_rows_do_not_train(self):
        rows = [Observation(A, DAY0, BEFORE, "a" * 64), Observation(A, DAY1, None, "a" * 64)]
        result = run([replace(target(), previous_cutoff=FIRST)], [source(R1, rows)], [A])
        self.assertEqual((result.decisions[0].state, result.decisions[0].new_days), ("REUSE_APPROVED_MODEL", 0))

    def test_fresh_edition_does_not_make_an_old_observation_new(self):
        result = run([replace(target(), previous_cutoff=FIRST)],
                     [source(R1, [Observation(A, DAY0, BEFORE, "a" * 64)], available=NOW)], [A])
        self.assertEqual((result.decisions[0].state, result.decisions[0].new_days), ("REUSE_APPROVED_MODEL", 0))

    def test_settlement_day_waits_until_kst_midnight(self):
        before_kst = datetime(2026, 1, 1, 14, 59, tzinfo=timezone.utc)
        at_kst = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
        forged = source(R1, [Observation(A, DAY1, before_kst, "a" * 64)], available=before_kst)
        result = plan_updates((target(),), (forged,), frozenset(), as_of=before_kst)
        self.assertEqual((result.decisions[0].state, result.fetch), ("AWAITING_SETTLEMENT_DAY", ()))
        result = plan_updates((target(),), (), frozenset(), as_of=at_kst)
        self.assertEqual((result.decisions[0].state, result.fetch), ("AWAITING_ACQUISITION", (R1,)))
        self.assertEqual(run([target()], [forged]).decisions[0].state, "UNVERIFIED_ACQUISITION")

    def test_unparsed_differs_from_verified_empty(self):
        for receipt, state in ((replace(source(R1), eligible_rows=None), "UNVERIFIED_ACQUISITION"),
                               (source(R1), "REUSE_APPROVED_MODEL")):
            result = run([target()], [receipt], [A])
            self.assertEqual((result.decisions[0].state, result.decisions[0].new_days), (state, 0))

    def test_chronology_or_lineage_fault_holds_whole_receipt(self):
        valid = Observation(A, DAY1, FIRST, "a" * 64)
        for invalid in (replace(valid, source_sha256="b" * 64),
                        replace(valid, trade_day=DAY2),
                        replace(valid, available_at=BEFORE),
                        replace(valid, available_at=NOW),
                        replace(valid, available_at=datetime(2026, 1, 2))):
            with self.subTest(invalid=invalid):
                receipt = replace(source(R1), eligible_rows=(valid, invalid))
                result = run([target()], [receipt], [A])
                self.assertEqual((result.decisions[0].state, result.decisions[0].new_days),
                                 ("UNVERIFIED_ACQUISITION", 0))

    def test_cutoffs_and_target_conflicts_fail_closed(self):
        with self.assertRaises(ValueError):
            run([target(), target()])
        with self.assertRaises(ValueError):
            run([replace(target(), previous_cutoff=FUTURE)])
        with self.assertRaises(ValueError):
            target(requests=(replace(R1, market="other"),))


if __name__ == "__main__":
    unittest.main()
