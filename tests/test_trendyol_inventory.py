import unittest
from unittest.mock import Mock, call, patch

from core.security import encrypt_secret
from core.seller_models import SellerProfile
from core.trendyol_inventory import (
    InventoryProduct,
    fetch_inventory,
    update_inventory,
)


class TestTrendyolInventory(unittest.TestCase):
    def setUp(self):
        self.profile = SellerProfile(
            seller_id="123456",
            name="Test Seller",
            api_key=encrypt_secret("test-key"),
            api_secret=encrypt_secret("test-secret"),
        )

    @staticmethod
    def _response(data, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    def _api_patches(self):
        return (
            patch("trendyol_labels.BASE_URL", "https://example.test/integration"),
            patch("trendyol_labels.api_headers", return_value=("123456", {"Authorization": "test"})),
        )

    def test_fetch_inventory_flattens_variants_and_paginates(self):
        first_page = self._response(
            {
                "totalPages": 2,
                "content": [
                    {
                        "title": "Product one",
                        "variants": [
                            {"barcode": "BC-1", "quantity": 8, "stockCode": "SKU-1"},
                            {"barcode": "BC-2", "quantity": 4, "stockCode": "SKU-2"},
                        ],
                    }
                ],
            }
        )
        second_page = self._response(
            {
                "totalPages": 2,
                "content": [
                    {
                        "productMainId": "Product two",
                        "variants": [{"barcode": "BC-3", "quantity": 0}],
                    }
                ],
            }
        )
        base_url_patch, headers_patch = self._api_patches()
        with base_url_patch, headers_patch:
            with patch(
                "core.trendyol_inventory.requests.request",
                side_effect=[first_page, second_page],
            ) as request:
                products = fetch_inventory(self.profile)

        self.assertEqual(
            products,
            [
                InventoryProduct("BC-1", 8, "SKU-1", "Product one"),
                InventoryProduct("BC-2", 4, "SKU-2", "Product one"),
                InventoryProduct("BC-3", 0, "", "Product two"),
            ],
        )
        self.assertEqual(
            [item.kwargs["params"]["page"] for item in request.call_args_list],
            [0, 1],
        )

    def test_fetch_inventory_uses_next_page_token_after_ten_thousand_rows(self):
        first_page = self._response(
            {
                "totalPages": 1,
                "nextPageToken": "continuation",
                "content": [{"variants": [{"barcode": "BC-1", "quantity": 2}]}],
            }
        )
        continuation_page = self._response(
            {
                "totalPages": 1,
                "content": [{"variants": [{"barcode": "BC-2", "quantity": 3}]}],
            }
        )
        base_url_patch, headers_patch = self._api_patches()
        with base_url_patch, headers_patch:
            with patch(
                "core.trendyol_inventory.requests.request",
                side_effect=[first_page, continuation_page],
            ) as request:
                products = fetch_inventory(self.profile)

        self.assertEqual([product.barcode for product in products], ["BC-1", "BC-2"])
        self.assertEqual(
            request.call_args_list[1].kwargs["params"],
            {"size": 100, "nextPageToken": "continuation"},
        )

    def test_update_submits_quantity_only_and_reports_batch_success(self):
        submitted = self._response({"batchRequestId": "batch-123"})
        completed = self._response(
            {
                "items": [
                    {
                        "requestItem": {"barcode": "BC-1", "quantity": 0},
                        "status": "SUCCESS",
                        "failureReasons": [],
                    }
                ]
            }
        )
        base_url_patch, headers_patch = self._api_patches()
        with base_url_patch, headers_patch:
            with patch(
                "core.trendyol_inventory.requests.request",
                side_effect=[submitted, completed],
            ) as request:
                result = update_inventory(
                    self.profile,
                    [{"barcode": "BC-1", "quantity": 0}],
                )

        self.assertEqual(result.successful_barcodes, ("BC-1",))
        self.assertEqual(result.failures, ())
        self.assertEqual(result.pending_barcodes, ())
        self.assertEqual(
            request.call_args_list[0],
            call(
                "POST",
                "https://example.test/integration/inventory/sellers/123456/products/price-and-inventory",
                headers={"Authorization": "test"},
                params=None,
                timeout=(5, 30),
                json={"items": [{"barcode": "BC-1", "quantity": 0}]},
            ),
        )

    def test_update_rejects_out_of_range_quantity_without_request(self):
        with patch("core.trendyol_inventory.requests.request") as request:
            with self.assertRaisesRegex(ValueError, "between 0 and 20000"):
                update_inventory(
                    self.profile,
                    [{"barcode": "BC-1", "quantity": 20001}],
                )

        request.assert_not_called()

    def test_update_reports_per_barcode_failures(self):
        submitted = self._response({"batchRequestId": "batch-456"})
        completed = self._response(
            {
                "items": [
                    {
                        "requestItem": {"barcode": "BC-1"},
                        "status": "FAILED",
                        "failureReasons": ["Invalid barcode"],
                    }
                ]
            }
        )
        base_url_patch, headers_patch = self._api_patches()
        with base_url_patch, headers_patch:
            with patch(
                "core.trendyol_inventory.requests.request",
                side_effect=[submitted, completed],
            ):
                result = update_inventory(
                    self.profile,
                    [{"barcode": "BC-1", "quantity": 2}],
                )

        self.assertEqual(result.failures, (("BC-1", "Invalid barcode"),))


if __name__ == "__main__":
    unittest.main()
