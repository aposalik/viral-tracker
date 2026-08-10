"""
Viral Product Tracker — main orchestrator
Sources: CJ hot products + Google Trends discovery + TikTok signal + AliExpress
Run: python scraper/main.py
Output: docs/products.json
"""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

from cj import get_access_token, get_cj_products_as_base, search_product
from trends import discover_trending_keywords, enrich_with_trend_score
from tiktok import get_tiktok_signal_keywords
from aliexpress import get_aliexpress_bestsellers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "products.json"
TOP_N = 25


def normalize_cj_result(result: dict, source: str) -> dict | None:
    """Convert a raw CJ search result into the standard product dict."""
    raw_price = str(result.get("sellPrice") or "0")
    sell_price = float(raw_price.split("--")[0].strip() or 0)
    if sell_price <= 0:
        return None
    name = result.get("productNameEn") or result.get("productName", "")
    if not name or len(name) < 4:
        return None
    return {
        "name": name,
        "category": result.get("categoryName", "General"),
        "rank_change_pct": 0,
        "asin": "",
        "url": "",
        "source": source,
        "cj_price": sell_price,
        "cj_shipping_days": result.get("shippingTime", "7-15"),
        "cj_product_id": result.get("pid", ""),
        "cj_image_url": result.get("productImage", ""),
    }


def lookup_keywords_on_cj(keywords: list[str], token: str, source: str, limit: int = 15) -> list[dict]:
    """Search CJ for each keyword and return normalized product dicts."""
    products = []
    for kw in keywords[:limit]:
        try:
            result = search_product(kw, token)
            if result:
                p = normalize_cj_result(result, source)
                if p:
                    products.append(p)
        except Exception as e:
            logger.warning(f"CJ lookup failed for '{kw}': {e}")
        time.sleep(0.4)
    logger.info(f"{source}: {len(products)} products found on CJ")
    return products


def score_product(p: dict) -> float:
    """
    Composite virality score (0-200):
      - Google Trends score: 0-100
      - CJ price attractiveness (sweet spot $5-$25)
      - Bonus for having a product image
      - Source bonus: tiktok/aliexpress signals get a small boost
    """
    trend = p.get("trend_score", 0)

    price = p.get("cj_price") or 0
    if 5 <= price <= 25:
        price_score = 60
    elif 25 < price <= 50:
        price_score = 40
    elif price < 5:
        price_score = 20
    else:
        price_score = 10

    image_bonus = 20 if p.get("cj_image_url") else 0

    source_bonus = 10 if p.get("source") in ("tiktok_signal", "aliexpress", "google_trends") else 0

    return round(trend + price_score + image_bonus + source_bonus, 1)


def estimate_margin(cj_price: float | None) -> str:
    if not cj_price or cj_price <= 0:
        return "N/A"
    retail_low = cj_price * 2.5
    retail_high = cj_price * 3.0
    costs_low = cj_price + retail_low * 0.28
    costs_high = cj_price + retail_high * 0.28
    margin_low = max(0, (retail_low - costs_low) / retail_low * 100)
    margin_high = max(0, (retail_high - costs_high) / retail_high * 100)
    return f"{int(margin_low)}-{int(margin_high)}%"


def run():
    logger.info("=== Viral Product Tracker starting ===")

    token = get_access_token()
    if not token:
        logger.error("No CJ token — cannot fetch products. Set CJ_API_KEY.")
        raise SystemExit(1)

    all_products: list[dict] = []

    # --- Source 1: CJ hot products ---
    logger.info("--- Source 1: CJ Hot Products ---")
    cj_products = get_cj_products_as_base(token)
    all_products.extend(cj_products)

    # --- Source 2: Google Trends discovery ---
    logger.info("--- Source 2: Google Trends Discovery ---")
    trend_keywords = discover_trending_keywords()
    all_products.extend(lookup_keywords_on_cj(trend_keywords, token, source="google_trends"))

    # --- Source 3: TikTok signal ---
    logger.info("--- Source 3: TikTok Signal ---")
    tiktok_keywords = get_tiktok_signal_keywords()
    all_products.extend(lookup_keywords_on_cj(tiktok_keywords, token, source="tiktok_signal"))

    # --- Source 4: AliExpress bestsellers ---
    logger.info("--- Source 4: AliExpress Bestsellers ---")
    ae_names = get_aliexpress_bestsellers()
    all_products.extend(lookup_keywords_on_cj(ae_names, token, source="aliexpress"))

    # Deduplicate by CJ product ID (keep first occurrence = highest priority source)
    seen: set[str] = set()
    unique: list[dict] = []
    for p in all_products:
        key = p.get("cj_product_id") or p["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    logger.info(f"Total unique products across all sources: {len(unique)}")

    # Filter junk
    products = [p for p in unique if p["name"] and len(p["name"]) > 3]

    # Enrich with Google Trends scores (cap at 50 to stay under rate limits)
    logger.info("Enriching with Google Trends scores...")
    products = enrich_with_trend_score(products[:50])

    # Score and rank
    for p in products:
        p["virality_score"] = score_product(p)
        p["estimated_margin"] = estimate_margin(p.get("cj_price"))

    products.sort(key=lambda x: x["virality_score"], reverse=True)
    top = products[:TOP_N]

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scanned": len(products),
        "sources": {
            "cj_hot": sum(1 for p in products if p.get("source") == "cj_hot"),
            "google_trends": sum(1 for p in products if p.get("source") == "google_trends"),
            "tiktok_signal": sum(1 for p in products if p.get("source") == "tiktok_signal"),
            "aliexpress": sum(1 for p in products if p.get("source") == "aliexpress"),
        },
        "products": top,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(top)} products to {OUTPUT_PATH}")
    logger.info(f"Sources breakdown: {payload['sources']}")
    logger.info("=== Done ===")


if __name__ == "__main__":
    run()
