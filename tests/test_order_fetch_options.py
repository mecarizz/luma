import unittest
from datetime import datetime
from unittest.mock import patch

from core.security import encrypt_secret
from core.seller_models import SellerProfile
from trendyol_labels import fetch_packages
from ui_orders import _FetchOrdersWorker


class TestOrderFetchOptions(unittest.TestCase):
    def _profile(self, seller_id):
        return SellerProfile(
            seller_id=seller_id,
            api_key=encrypt_secret("test-key"),
            api_secret=encrypt_secret("test-secret"),
            statuses=["Created", "Picking"],
            lookback_hours=48,
        )

    def test_manual_fetch_uses_selected_days_and_caps_total_across_sellers(self):
        profiles = [self._profile("123456"), self._profile("654321")]
        results = []
        worker = _FetchOrdersWorker(profiles, lookback_days=7, max_orders=5)
        worker.completed.connect(results.append)
        first_seller_packages = [{"shipmentPackageId": index} for index in range(3)]
        second_seller_packages = [{"shipmentPackageId": index} for index in range(3, 5)]

        with patch(
            "trendyol_labels.fetch_packages",
            side_effect=[first_seller_packages, second_seller_packages],
        ) as fetch:
            worker.run()

        self.assertEqual(len(results[0][0]), 5)
        self.assertEqual(fetch.call_args_list[0].args[:2], (["Created", "Picking"], 7))
        self.assertEqual(fetch.call_args_list[0].kwargs["max_orders"], 5)
        self.assertEqual(fetch.call_args_list[1].args[:2], (["Created", "Picking"], 7))
        self.assertEqual(fetch.call_args_list[1].kwargs["max_orders"], 2)

    def test_bookkeeping_fetch_passes_custom_dates(self):
        profile = self._profile("123456")
        start = datetime(2026, 11, 1)
        end = datetime(2026, 11, 8)
        worker = _FetchOrdersWorker(
            [profile],
            max_orders=10000,
            start_date=start,
            end_date=end,
            all_statuses=True,
        )

        with patch("trendyol_labels.fetch_packages", return_value=[]) as fetch:
            worker.run()

        self.assertIsNone(fetch.call_args.args[0])
        self.assertEqual(fetch.call_args.kwargs["start_date"], start)
        self.assertEqual(fetch.call_args.kwargs["end_date"], end)

    def test_fetch_stops_pagination_at_max_order_count(self):
        seller = {"id": "123456", "key": "key", "secret": "secret", "name": "Test"}
        page = {
            "content": [
                {"shipmentPackageId": 1},
                {"shipmentPackageId": 2},
                {"shipmentPackageId": 3},
            ],
            "totalPages": 2,
        }

        with patch("trendyol_labels.api_headers", return_value=("123456", {})):
            with patch("trendyol_labels.orders_url", return_value="orders-url"):
                with patch("trendyol_labels._get", return_value=page) as get:
                    packages = fetch_packages(
                        ["Picking"],
                        days=7,
                        seller=seller,
                        max_orders=2,
                    )

        self.assertEqual([package["shipmentPackageId"] for package in packages], [1, 2])
        get.assert_called_once()

    def test_fetch_rejects_non_positive_order_limit(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            fetch_packages(["Picking"], seller={}, max_orders=0)

    def test_fetch_uses_custom_date_range(self):
        start = datetime(2026, 11, 1)
        end = datetime(2026, 11, 3)
        seller = {"id": "123456", "key": "key", "secret": "secret", "name": "Test"}
        page = {"content": [{"shipmentPackageId": 1}], "totalPages": 1}

        with patch("trendyol_labels.api_headers", return_value=("123456", {})):
            with patch("trendyol_labels.orders_url", return_value="orders-url"):
                with patch("trendyol_labels._get", return_value=page) as get:
                    fetch_packages(
                        ["Picking"],
                        seller=seller,
                        start_date=start,
                        end_date=end,
                    )

        self.assertEqual(
            get.call_args.args[2]["startDate"],
            int(start.timestamp() * 1000),
        )
        self.assertEqual(
            get.call_args.args[2]["endDate"],
            int(end.timestamp() * 1000),
        )

    def test_fetch_without_status_filter_queries_all_statuses(self):
        start = datetime(2026, 11, 1)
        end = datetime(2026, 11, 2)
        seller = {"id": "123456", "key": "key", "secret": "secret", "name": "Test"}
        page = {"content": [{"shipmentPackageId": 1}], "totalPages": 1}

        with patch("trendyol_labels.api_headers", return_value=("123456", {})):
            with patch("trendyol_labels.orders_url", return_value="orders-url"):
                with patch("trendyol_labels._get", return_value=page) as get:
                    packages = fetch_packages(
                        None,
                        seller=seller,
                        start_date=start,
                        end_date=end,
                    )

        self.assertEqual(len(packages), 1)
        self.assertNotIn("status", get.call_args.args[2])

    def test_fetch_splits_custom_ranges_into_api_windows(self):
        start = datetime(2026, 11, 1)
        end = datetime(2026, 11, 20)
        seller = {"id": "123456", "key": "key", "secret": "secret", "name": "Test"}
        page = {"content": [], "totalPages": 1}

        with patch("trendyol_labels.api_headers", return_value=("123456", {})):
            with patch("trendyol_labels.orders_url", return_value="orders-url"):
                with patch("trendyol_labels._get", return_value=page) as get:
                    fetch_packages(
                        ["Picking"],
                        seller=seller,
                        start_date=start,
                        end_date=end,
                    )

        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[0].args[2]["startDate"],
            int(start.timestamp() * 1000),
        )
        self.assertEqual(
            get.call_args_list[1].args[2]["endDate"],
            int(end.timestamp() * 1000),
        )


if __name__ == "__main__":
    unittest.main()
