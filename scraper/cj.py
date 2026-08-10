import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"
_token_cache: dict = {}


def get_access_token() -> str | None:
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > time.time():
        return _token_cache["token"]

    api_key = os.environ.get("CJ_API_KEY")

    if not api_key:
        logger.warning("CJ_API_KEY not set — skipping CJ lookup")
        return None

    try:
        resp = requests.post(
            f"{CJ_BASE}/authentication/getAccessToken",
            json={"apiKey": api_key},
            timeout=10,
        )
        data = resp.json()
        logger.info(f"CJ auth response: result={data.get('result')} message={data.get('message')} code={data.get('code')}")
        if data.get("result"):
            token = data["data"]["accessToken"]
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + 82800
            return token
        logger.warning(f"CJ auth failed: {data.get('message')}")
    except Exception as e:
        logger.warning(f"CJ auth error: {e}")

    return None


def get_hot_products(token: str, page: int = 1, page_size: int = 50) -> list[dict]:
    """Fetch CJ's own hot/trending product list."""
    try:
        resp = requests.get(
            f"{CJ_BASE}/product/list",
            headers={"CJ-Access-Token": token},
            params={"pageNum": page, "pageSize": page_size},
            timeout=15,
        )
        data = resp.json()
        logger.info(f"CJ product list response: result={data.get('result')} message={data.get('message')}")
        if data.get("result") and data["data"].get("list"):
            return data["data"]["list"]
    except Exception as e:
        logger.warning(f"CJ hot products fetch failed: {e}")
    return []


def search_product(name: str, token: str) -> dict | None:
    try:
        resp = requests.get(
            f"{CJ_BASE}/product/list",
            headers={"CJ-Access-Token": token},
            params={"productName": name, "pageNum": 1, "pageSize": 5},
            timeout=10,
        )
        data = resp.json()
        if data.get("result") and data["data"]["list"]:
            return data["data"]["list"][0]
    except Exception as e:
        logger.warning(f"CJ search failed for '{name}': {e}")
    return None


def get_cj_products_as_base(token: str) -> list[dict]:
    """
    Use CJ hot products as the primary data source.
    Returns normalized product dicts compatible with the scorer.
    """
    raw = get_hot_products(token, page_size=80)
    products = []

    for item in raw:
        raw_price = str(item.get("sellPrice") or "0")
        sell_price = float(raw_price.split("--")[0].strip() or 0)
        if sell_price <= 0:
            continue

        products.append({
            "name": item.get("productNameEn") or item.get("productName", ""),
            "category": item.get("categoryName", "General"),
            "rank_change_pct": 0,          # no Amazon data — will be enriched by trends
            "asin": "",
            "url": "",
            "source": "cj_hot",
            "cj_price": sell_price,
            "cj_shipping_days": item.get("shippingTime", "7-15"),
            "cj_product_id": item.get("pid", ""),
            "cj_image_url": item.get("productImage", ""),
        })

    logger.info(f"Got {len(products)} products from CJ hot list")
    return products


def enrich_with_cj(products: list[dict]) -> list[dict]:
    """Enrich Amazon-sourced products with CJ supplier data."""
    token = get_access_token()
    if not token:
        for p in products:
            p.update({"cj_price": None, "cj_shipping_days": None,
                       "cj_product_id": None, "cj_image_url": None})
        return products

    for p in products:
        result = search_product(p["name"], token)
        if result:
            p["cj_price"] = float(result.get("sellPrice", 0))
            p["cj_shipping_days"] = result.get("shippingTime", "7-15")
            p["cj_product_id"] = result.get("pid", "")
            p["cj_image_url"] = result.get("productImage", "")
        else:
            p.update({"cj_price": None, "cj_shipping_days": None,
                       "cj_product_id": None, "cj_image_url": None})
        time.sleep(0.5)

    return products
