"""Read and update a seller's approved Trendyol inventory."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests

from core.seller_models import SellerProfile

PAGE_SIZE = 100
MAX_UPDATE_ITEMS = 1000
MAX_SELLABLE_QUANTITY = 20000


@dataclass(frozen=True)
class InventoryProduct:
    barcode: str
    quantity: Optional[int]
    stock_code: str
    title: str


@dataclass(frozen=True)
class InventoryUpdateResult:
    batch_request_id: str
    successful_barcodes: Tuple[str, ...]
    failures: Tuple[Tuple[str, str], ...]
    pending_barcodes: Tuple[str, ...]
    status_error: Optional[str] = None


def _api_context(profile: SellerProfile) -> Tuple[str, str, Dict[str, str]]:
    credential_error = profile.credential_error
    if credential_error:
        raise ValueError(f"{profile.display_tag}: {credential_error}")

    import trendyol_labels as labels

    seller = {
        "id": profile.seller_id,
        "key": profile.raw_api_key,
        "secret": profile.raw_api_secret,
        "name": profile.name,
    }
    seller_id, headers = labels.api_headers(seller)
    return labels.BASE_URL.rstrip("/"), quote(seller_id, safe=""), headers


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, object]] = None,
    payload: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    request_options: Dict[str, object] = {
        "headers": headers,
        "params": params,
        "timeout": (5, 30),
    }
    if payload is not None:
        request_options["json"] = payload

    try:
        response = requests.request(method, url, **request_options)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Trendyol inventory request failed ({type(exc).__name__})."
        ) from exc

    if response.status_code in (401, 403):
        raise RuntimeError(
            "Trendyol rejected the inventory request. Check the seller credentials "
            "and product/inventory API permissions."
        )
    if response.status_code == 429:
        raise RuntimeError("Trendyol rate-limited the inventory request. Try again later.")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Trendyol inventory request failed with HTTP {response.status_code}."
        ) from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Trendyol returned invalid JSON for the inventory request.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Trendyol returned an unexpected inventory response.")
    return data


def fetch_inventory(profile: SellerProfile) -> List[InventoryProduct]:
    """Fetch approved inventory, following page numbers and any continuation token."""
    base_url, seller_id, headers = _api_context(profile)
    url = (
        f"{base_url}/product/sellers/{seller_id}/products/"
        "approved/inventory-and-price"
    )
    products: List[InventoryProduct] = []
    seen_barcodes = set()
    page = 0
    next_page_token: Optional[str] = None
    seen_tokens = set()

    while True:
        params: Dict[str, object] = {"size": PAGE_SIZE}
        if next_page_token is None:
            params["page"] = page
        else:
            params["nextPageToken"] = next_page_token

        data = _request_json("GET", url, headers, params=params)
        content = data.get("content")
        total_pages = data.get("totalPages")
        if (
            not isinstance(content, list)
            or not isinstance(total_pages, int)
            or isinstance(total_pages, bool)
            or total_pages < 0
        ):
            raise RuntimeError("Trendyol returned an incomplete inventory page.")

        for product in content:
            if not isinstance(product, dict):
                raise RuntimeError("Trendyol returned an invalid inventory product.")
            variants = product.get("variants")
            if not isinstance(variants, list):
                raise RuntimeError("Trendyol returned an invalid inventory variant list.")
            for variant in variants:
                if not isinstance(variant, dict):
                    raise RuntimeError("Trendyol returned an invalid inventory variant.")
                barcode = str(variant.get("barcode") or "").strip()
                if not barcode:
                    raise RuntimeError("Trendyol returned an inventory item without a barcode.")
                if barcode in seen_barcodes:
                    raise RuntimeError(
                        f"Trendyol returned duplicate inventory barcode {barcode}."
                    )
                seen_barcodes.add(barcode)
                quantity = variant.get("quantity")
                if quantity is not None and (
                    not isinstance(quantity, int) or isinstance(quantity, bool)
                ):
                    raise RuntimeError(
                        f"Trendyol returned an invalid stock quantity for barcode {barcode}."
                    )
                title = (
                    product.get("title")
                    or product.get("productName")
                    or product.get("productMainId")
                    or ""
                )
                products.append(
                    InventoryProduct(
                        barcode=barcode,
                        quantity=quantity,
                        stock_code=str(variant.get("stockCode") or ""),
                        title=str(title),
                    )
                )

        if next_page_token is not None:
            token = data.get("nextPageToken")
            if token is None:
                break
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise RuntimeError("Trendyol returned an invalid inventory page token.")
            next_page_token = token
            seen_tokens.add(token)
            continue

        if page + 1 < total_pages:
            page += 1
            continue

        token = data.get("nextPageToken")
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen_tokens:
            raise RuntimeError("Trendyol returned an invalid inventory page token.")
        next_page_token = token
        seen_tokens.add(token)

    return products


def _validated_updates(updates: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    items = list(updates)
    if not items:
        raise ValueError("There are no stock changes to submit.")
    if len(items) > MAX_UPDATE_ITEMS:
        raise ValueError(
            f"Trendyol accepts at most {MAX_UPDATE_ITEMS} stock updates per request."
        )

    validated: List[Dict[str, object]] = []
    seen_barcodes = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every stock update must be an object with a barcode and quantity.")
        barcode = str(item.get("barcode") or "").strip()
        quantity = item.get("quantity")
        if not barcode:
            raise ValueError("Every stock update must include a barcode.")
        if barcode in seen_barcodes:
            raise ValueError(f"Stock update contains duplicate barcode {barcode}.")
        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity < 0
            or quantity > MAX_SELLABLE_QUANTITY
        ):
            raise ValueError(
                f"Stock quantity for barcode {barcode} must be between 0 and "
                f"{MAX_SELLABLE_QUANTITY}."
            )
        seen_barcodes.add(barcode)
        validated.append({"barcode": barcode, "quantity": quantity})
    return validated


def update_inventory(
    profile: SellerProfile,
    updates: Iterable[Dict[str, object]],
    poll_interval: float = 2.0,
    timeout: float = 120.0,
) -> InventoryUpdateResult:
    """Submit quantity-only changes and poll Trendyol until item results are available."""
    if poll_interval <= 0 or timeout <= 0:
        raise ValueError("Inventory update polling requires a positive timeout and interval.")
    items = _validated_updates(updates)
    base_url, seller_id, headers = _api_context(profile)
    update_url = (
        f"{base_url}/inventory/sellers/{seller_id}/products/price-and-inventory"
    )
    try:
        submitted = _request_json(
            "POST",
            update_url,
            headers,
            payload={"items": items},
        )
    except RuntimeError as exc:
        raise RuntimeError(f"Could not submit stock changes: {exc}") from exc

    batch_request_id = str(submitted.get("batchRequestId") or "").strip()
    if not batch_request_id:
        raise RuntimeError("Trendyol accepted no batch ID for the stock update request.")

    batch_url = (
        f"{base_url}/product/sellers/{seller_id}/products/"
        f"batch-requests/{quote(batch_request_id, safe='')}"
    )
    requested_barcodes = {str(item["barcode"]) for item in items}
    terminal: Dict[str, Tuple[str, str]] = {}
    status_error: Optional[str] = None
    deadline = time.monotonic() + timeout

    while True:
        try:
            result = _request_json("GET", batch_url, headers)
        except RuntimeError as exc:
            status_error = str(exc)
            break
        result_items = result.get("items")
        if not isinstance(result_items, list):
            raise RuntimeError(
                f"Stock update batch {batch_request_id} returned invalid item results."
            )
        for result_item in result_items:
            if not isinstance(result_item, dict):
                raise RuntimeError(
                    f"Stock update batch {batch_request_id} returned an invalid item result."
                )
            request_item = result_item.get("requestItem")
            barcode = (
                str(request_item.get("barcode") or "").strip()
                if isinstance(request_item, dict)
                else ""
            )
            status = str(result_item.get("status") or "").upper()
            if barcode not in requested_barcodes or status not in ("SUCCESS", "FAILED"):
                continue
            if status == "SUCCESS":
                terminal[barcode] = (status, "")
            else:
                reasons = result_item.get("failureReasons") or []
                detail = "; ".join(str(reason) for reason in reasons) or "Trendyol rejected the update."
                terminal[barcode] = (status, detail)

        if requested_barcodes.issubset(terminal):
            break
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            break
        time.sleep(min(poll_interval, remaining_time))

    successful = tuple(
        barcode for barcode in requested_barcodes
        if terminal.get(barcode, ("", ""))[0] == "SUCCESS"
    )
    failures = tuple(
        (barcode, terminal[barcode][1])
        for barcode in requested_barcodes
        if terminal.get(barcode, ("", ""))[0] == "FAILED"
    )
    pending = tuple(sorted(requested_barcodes.difference(terminal)))
    return InventoryUpdateResult(
        batch_request_id=batch_request_id,
        successful_barcodes=tuple(sorted(successful)),
        failures=tuple(sorted(failures)),
        pending_barcodes=pending,
        status_error=status_error,
    )
