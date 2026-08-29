from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.kis import KISClient  # noqa: E402


class KISPendingOrdersTests(unittest.TestCase):
    def test_mock_has_no_broker_pending_orders(self) -> None:
        client = object.__new__(KISClient)
        client.mode = "mock"
        self.assertEqual([], client.get_pending_orders())

    def test_paper_queries_only_unfilled_domestic_orders(self) -> None:
        client = object.__new__(KISClient)
        client.mode = "live"
        client.env = "paper"
        client.account = "12345678"
        payload = {
            "output1": [{
                "odno": "0001",
                "pdno": "005930",
                "prdt_name": "삼성전자",
                "sll_buy_dvsn_cd": "02",
                "ord_qty": "3",
                "rmn_qty": "2",
                "ord_unpr": "70000",
                "ord_tmd": "101500",
            }]
        }
        with mock.patch.object(client, "_call", return_value=payload) as call:
            result = client.get_pending_orders()

        path, tr_id, params = call.call_args.args
        self.assertEqual(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", path
        )
        self.assertEqual("VTTC8001R", tr_id)
        self.assertEqual("02", params["CCLD_DVSN"])
        self.assertEqual("12345678", params["CANO"])
        self.assertEqual("buy", result[0]["side"])
        self.assertEqual(2, result[0]["qty"])


if __name__ == "__main__":
    unittest.main()
