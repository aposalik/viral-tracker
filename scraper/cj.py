import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"
_token_cache: dict = {}


def get_access_token() -> str | None:
    """
    Get a CJ Dropshipping API access token using env credentials.
    Caches until expiry.
    """
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > time.time():
        return _token_cache["token"]

    email = os.environ.get("CJ_EMAIL")
    password = os.environ.get("CJ_PASSWORD")

    if not email or not password:
        logger.warning("CJ_EMAIL / CJ_PASSWORD not set — skipping CJ lookup")
        return None

    try:
        resp = requests.post(
            f"{CJ_BASE}/authentication/getAccessToken",
            json={"email": email, "password": password},
            timeout=10,
        )
        data = resp.json()
        if data.get("result"):
            token = data["data"]["accessToken"]
            # CJ tokens last 24h; cache for 23h to be safe
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + 82800
            return token
        logger.warning(f"CJ auth failed: {data.get('message')}")
    except Exception as e:
        logger.warning(f"CJ auth error: {e}")

    return None


def search_product(name: str, token: str) -> dict | None:
    """
    Search CJ for a product by name. Returns the best match dict or None.
    """
    try:
        resp = requests.get(
            f"{CJ_BASE}/product/list",
            headers={"CJ-Access-Token": token},
            params={
                "productName": name,
                "pageNum": 1,
                "pageSize": 5,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("result") and data["data"]["list"]:
            return data["data"]["list"][0]
    except Exception as e:
        logger.warning(f"CJ search failed for '{name}': {e}")

    return None


def enrich_with_cj(products: list[dict]) -> list[dict]:
    """
    For each product, find a matching CJ supplier and attach:
    cj_price, cj_shipping_days, cj_product_id, cj_image_url
    """
    token = get_access_token()
    if not token:
        for p in products:
            p["cj_price"] = None
            p["cj_shipping_days"] = None
            p["cj_product_id"] = None
            p["cj_image_url"] = None
        return products

    for p in products:
        result = search_product(p["name"], token)
        if result:
            p["cj_price"] = float(result.get("sellPrice", 0))
            p["cj_shipping_days"] = result.get("shippingTime", "7-15")
            p["cj_product_id"] = result.get("pid", "")
            p["cj_image_url"] = result.get("productImage", "")
        else:
            p["cj_price"] = None
            p["cj_shipping_days"] = None
            p["cj_product_id"] = None
            p["cj_image_url"] = None

        time.sleep(0.5)  # CJ rate limit is generous but be polite

    return products
