import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ml.price_forecast.at_auction import (
    AuctionCodebook, AuctionError, AuctionQuery, PageCapture, fetch_edition, load_codebook, parse_edition,
)
from ml.price_forecast.auction_archive import collect, load_editions
from ml.price_forecast.auction_history import reconcile_auction_editions
from ml.price_forecast.baseline import load_daily_prices

# Synthetic wire fixtures, with no publisher credential or historical market data.
DAY = date(2026, 1, 1)
NOW = datetime(2026, 1, 2, 5, tzinfo=timezone.utc)
QUERY = AuctionQuery(DAY, "01", "00001101", "04", "08", "02")
CODES = AuctionCodebook(
    "a" * 64, frozenset({"01"}), frozenset({("01", "00001101")}), frozenset({("08", "04", "02")}),
    frozenset({"05"}), frozenset({"11"}), frozenset({"101"}), frozenset({"100"}), frozenset({"12", "11"}),
)


def trade(**changes):
    row = {
        **QUERY.filters(),
        "plor_cd": "05", "grd_cd": "11", "unit_cd": "12", "pkg_cd": "101", "sz_cd": "100",
        "unit_qty": "2.000", "qty": "6.000", "scsbd_prc": "41000.000", "totprc": "246000.000",
        "unit_tot_qty": "12.000", "spm_no": 13, "auctn_seq": "0020", "auctn_seq2": 1,
        "trd_se": "경매", "scsbd_dt": "2026-01-01 09:21:00",
    }
    return {**row, **changes}


def page(rows, *, number=1, size=10, total=None, at=NOW, result="00", empty_string=False):
    payload = json.dumps({
        "response": {
            "header": {"resultCode": result},
            "body": {
                "pageNo": number, "numOfRows": size, "totalCount": len(rows) if total is None else total,
                "items": "" if empty_string else {"item": rows},
            },
        },
    }, ensure_ascii=False).encode()
    return PageCapture(number, size, at, payload)


def edition(*pages, query=QUERY):
    return parse_edition(query, pages, CODES)


class AuctionAdapterTests(unittest.TestCase):
    def test_bounded_wire_request_and_weighted_normalization(self):
        captures = [
            page([trade()], size=1, total=2),
            page([trade(spm_no=14)], number=2, size=1, total=2, at=NOW + timedelta(seconds=1)),
        ]
        calls = []
        ticks = iter([NOW, *(p.received_at for p in captures)])

        def transport(params):
            calls.append(params)
            return captures[len(calls) - 1].payload

        result = fetch_edition(QUERY, CODES, transport, size=1, max_pages=2, clock=lambda: next(ticks))
        self.assertEqual([call["pageNo"] for call in calls], ["1", "2"])
        self.assertEqual(calls[0]["cond[corp_cd::EQ]"], "00001101")
        self.assertEqual(calls[0]["cond[gds_sclsf_cd::EQ]"], "02")
        self.assertNotIn("serviceKey", calls[0])
        self.assertEqual(result.available_at, NOW + timedelta(seconds=1))
        self.assertEqual(result.code_evidence_sha256, CODES.evidence_sha256)
        self.assertEqual(result.captures[0].sha256, hashlib.sha256(captures[0].payload).hexdigest())
        self.assertEqual((result.input_rows, len(result.trades)), (2, 2))
        normalized = result.trades[0]
        self.assertEqual(normalized.trade_day, DAY)
        self.assertEqual(normalized.series.unit, "12:2:101:100")
        self.assertEqual(normalized.series.product, "08:04")
        self.assertEqual(normalized.trade_id[3], "0020")
        self.assertEqual((normalized.total_krw, normalized.volume_kg), (Decimal(246000), Decimal(12)))
        history = reconcile_auction_editions([result])
        self.assertEqual(history.prices[0].price_krw_per_kg, 20500)

    def test_empty_success_is_distinct_from_gateway_failure_and_wrong_scope(self):
        empty = edition(page([], empty_string=True))
        self.assertEqual((empty.input_rows, empty.trades, empty.rejections), (0, (), ()))
        for raw in (page([], result="30", empty_string=True), page([trade(whsl_mrkt_cd="02")]),
                    page([trade(trd_clcln_ymd="2026-01-02")]), page([trade(gds_sclsf_cd="99")])):
            with self.subTest(raw=raw), self.assertRaises(AuctionError):
                edition(raw)

    def test_ineligible_rows_are_reported_without_false_dates_or_kg_prices(self):
        result = edition(page([
            trade(spm_no=1, scsbd_dt=""),
            trade(spm_no=2, totprc="41000"),
            trade(spm_no=3, unit_cd="11"),
            trade(spm_no=4, unit_tot_qty="6"),
            trade(spm_no=5, gds_lclsf_cd="08", plor_cd="99"),
            trade(spm_no=None, trd_se="정가수의"),
        ]))
        self.assertEqual(result.input_rows, 6)
        self.assertFalse(result.trades)
        self.assertEqual([v.reason for v in result.rejections], [
            "MISSING_OR_INVALID_TRADE_TIME", "INCONSISTENT_AMOUNT_OR_VOLUME", "UNVERIFIED_MASS_UNIT",
            "INCONSISTENT_AMOUNT_OR_VOLUME", "CODE_OUTSIDE_REFERENCE", "NON_AUCTION_TRADE_TYPE",
        ])
        with self.assertRaisesRegex(ValueError, "MISSING_OR_INVALID_TRADE_TIME"):
            reconcile_auction_editions([result])

    def test_missing_changing_duplicate_or_out_of_order_pages_hold_edition(self):
        first = page([trade()], size=1, total=2)
        good_second = page([trade(spm_no=14)], number=2, size=1, total=2)
        wrong_total = page([trade(spm_no=14)], number=2, size=1, total=3)
        repeat_id = page([trade()], number=2, size=1, total=2)
        for captures in ((first,), (good_second, first), (first, wrong_total), (first, repeat_id),
                         (replace(first, number=True), good_second)):
            with self.subTest(captures=captures), self.assertRaises(AuctionError):
                edition(*captures)

    def test_repeated_excluded_row_cannot_hide_a_missing_auction_page(self):
        non_auction = trade(spm_no=None, trd_se="정가수의")
        pages = (
            page([non_auction], size=1, total=2),
            page([non_auction], number=2, size=1, total=2),
        )
        with self.assertRaisesRegex(AuctionError, "Repeated record"):
            edition(*pages)

    def test_deduplicate_identical_rows_and_reject_identity_collision(self):
        original = trade()
        result = edition(page([original, original.copy()]))
        self.assertEqual((result.input_rows, result.duplicate_rows, len(result.trades)), (2, 1, 1))
        with self.assertRaisesRegex(AuctionError, "Conflicting source record"):
            edition(page([original, trade(scsbd_prc="42000", totprc="252000")]))

    def test_unknown_selected_fields_and_duplicate_json_keys_hold_capture(self):
        with self.assertRaisesRegex(AuctionError, "unrequested"):
            edition(page([trade(unrequested="synthetic")]))
        good = page([trade()])
        with self.assertRaisesRegex(AuctionError, "Duplicate key"):
            edition(replace(good, payload=good.payload.replace(b'"qty": "6.000"', b'"qty": "6.000", "qty": "6"')))

    def test_refuse_to_fetch_beyond_approved_budget_or_with_unknown_market(self):
        calls = []

        def transport(params):
            calls.append(params)
            return page([trade()], size=1, total=3).payload

        with self.assertRaisesRegex(AuctionError, "approved page budget"):
            fetch_edition(QUERY, CODES, transport, size=1, max_pages=2, clock=lambda: NOW)
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(AuctionError, "Market absent"):
            fetch_edition(replace(QUERY, market="02"), CODES, transport, size=1, max_pages=2, clock=lambda: NOW)
        self.assertEqual(len(calls), 1)

    def test_code_reference_checks_exact_codes(self):
        raw = {
            "evidence_sha256": "a" * 64, "markets": ["01"], "corporations": [["01", "00001101"]],
            "products": [["08", "04", "02"]], "origins": ["05"], "grades": ["11"],
            "packages": ["101"], "sizes": ["100"], "units": ["11", "12"],
        }
        self.assertEqual(load_codebook(json.dumps(raw).encode()), CODES)
        raw["markets"] = [1]
        with self.assertRaises(AuctionError):
            load_codebook(json.dumps(raw).encode())


class AuctionArchiveTests(unittest.TestCase):
    def test_export_cli_replays_capture_and_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive, reference, evidence, output = (root / name for name in ("db", "codes.json", "source", "prices.csv"))
            evidence.write_bytes(b"synthetic standard-code evidence")
            codebook = {
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "markets": ["01"], "corporations": [["01", "00001101"]], "products": [["08", "04", "02"]],
                "origins": ["05"], "grades": ["11"], "packages": ["101"], "sizes": ["100"], "units": ["11", "12"],
            }
            reference.write_text(json.dumps(codebook))
            codes = load_codebook(reference.read_bytes())
            captured = parse_edition(QUERY, (page([trade()]),), codes)
            collect(archive, QUERY, codes, lambda: captured)
            command = [
                sys.executable, "-S", "-m", "ml.price_forecast.auction_archive", "--archive", str(archive),
                "--codebook", str(reference), "--code-evidence", str(evidence), "export",
                "--category", "08", "--product", "04", "--cultivar", "02", "--output", str(output),
            ]
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            payload = output.read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), report["normalized_csv_sha256"])
            self.assertEqual(report["normalized_rows"], 1)
            with output.open() as stream:
                normalized, = load_daily_prices(stream)
            self.assertEqual(normalized.price_krw_per_kg, 20500)
            self.assertIn(normalized.source_sha256, report["source_manifest"])
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), payload)

    def test_reuse_preserves_first_available_time_and_refresh_versions(self):
        original = edition(page([trade()]))
        identical = edition(page([trade()], at=NOW + timedelta(hours=1)))
        revised = edition(page([trade(scsbd_prc="42000", totprc="252000")], at=NOW + timedelta(hours=2)))
        reverted = edition(page([trade()], at=NOW + timedelta(hours=3)))
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "private.sqlite"
            self.assertEqual(collect(archive, QUERY, CODES, lambda: original), ("CAPTURED", original))
            self.assertEqual(collect(archive, QUERY, CODES, lambda: self.fail("used network on reuse")), ("REUSED", original))
            self.assertEqual(collect(archive, QUERY, CODES, lambda: identical, refresh=True), ("UNCHANGED", original))
            self.assertEqual(collect(archive, QUERY, CODES, lambda: revised, refresh=True), ("CAPTURED", revised))
            self.assertEqual(collect(archive, QUERY, CODES, lambda: reverted, refresh=True), ("CAPTURED", reverted))
            self.assertEqual(load_editions(archive, CODES), (original, revised, reverted))
            with self.assertRaisesRegex(AuctionError, "new capture must follow"):
                collect(archive, QUERY, CODES, lambda: revised, refresh=True)
            with self.assertRaisesRegex(AuctionError, "original standard-code reference"):
                load_editions(archive, replace(CODES, origins=frozenset({"99"})))

    def test_replay_detects_raw_payload_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "private.sqlite"
            collect(archive, QUERY, CODES, lambda: edition(page([trade()])))
            with sqlite3.connect(archive) as connection:
                pages = json.loads(connection.execute("SELECT pages FROM auction_editions").fetchone()[0])
                pages[0]["payload"] = "e30="
                connection.execute("UPDATE auction_editions SET pages = ?", (json.dumps(pages),))
            with self.assertRaisesRegex(AuctionError, "page hash mismatch"):
                load_editions(archive, CODES)


if __name__ == "__main__":
    unittest.main()
