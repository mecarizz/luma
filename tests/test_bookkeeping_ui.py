import unittest
from datetime import datetime
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from core.seller_models import SellerProfile
from ui_bookkeeping import BookkeepingTab, _bookkeeping_rows


class TestBookkeepingRows(unittest.TestCase):
    def test_builds_one_simplified_row_per_product_line(self):
        packages = [
            {
                "shipmentAddress": {
                    "fullName": "Customer One",
                    "district": "Esenyurt",
                    "city": "İstanbul",
                },
                "lines": [
                    {
                        "productName": "Loria pudra çift",
                        "quantity": 1,
                        "amount": 2999.99,
                    },
                    {
                        "productName": "Second product",
                        "quantity": 2,
                        "price": 10,
                    },
                ],
            }
        ]

        self.assertEqual(
            _bookkeeping_rows(packages),
            [
                ("Customer One", "Esenyurt/İstanbul", "Loria pudra çift", "2.999,99"),
                ("Customer One", "Esenyurt/İstanbul", "Second product x 2", "20,00"),
            ],
        )

    def test_missing_address_and_price_are_displayed_explicitly(self):
        packages = [{"lines": [{"barcode": "BC-1"}]}]

        self.assertEqual(
            _bookkeeping_rows(packages),
            [("—", "—", "BC-1", "—")],
        )


class TestBookkeepingTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selected_dates_are_fetched_as_inclusive_calendar_days(self):
        tab = BookkeepingTab()
        self.addCleanup(tab.close)
        profile = SellerProfile(seller_id="123456")
        manager = type("SellerManagerStub", (), {"list_all": lambda _self: [profile]})()
        tab.set_manager(manager)
        tab.start_date_input.setDate(QDate(2026, 11, 1))
        tab.end_date_input.setDate(QDate(2026, 11, 3))

        with patch("ui_bookkeeping._FetchOrdersWorker") as worker_type:
            tab.fetch_orders()

        self.assertEqual(
            worker_type.call_args.kwargs["start_date"],
            datetime(2026, 11, 1, 0, 0),
        )
        self.assertEqual(
            worker_type.call_args.kwargs["end_date"],
            datetime(2026, 11, 3, 23, 59, 59, 999000),
        )


if __name__ == "__main__":
    unittest.main()
