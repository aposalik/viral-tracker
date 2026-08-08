"""
Viral Product Tracker — main orchestrator
Data sources: CJ Dropshipping hot products + Google Trends enrichment
Run: python scraper/main.py
Output: docs/products.json
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from cj import get_access_token, get_cj_products_as_base
from trends import enrich_with_trend_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "products.json"
TOP_N = 25


def score_product(p: dict) -> float:
    """
    Composite virality score (0-200):
      - Google Trends score: 0-100
      - CJ price attractiveness: cheap items score higher (sweet spot $5-$25)
      - Bonus for having a real image
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

    return round(trend + price_score + image_bonus, 1)


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
        logger.error("No CJ token — cannot fetch products. Set CJ_EMAIL and CJ_PASSWORD.")
        return

    # 1. Pull CJ hot products as base
    logger.info("Fetching CJ hot products...")
    products = get_cj_products_as_base(token)

    if not products:
        logger.error("No products from CJ — aborting")
        return

    # Filter out products with no name or bad data
    products = [p for p in products if p["name"] and len(p["name"]) > 3]

    # 2. Enrich with Google Trends scores (sample 40 to stay under rate limits)
    logger.info("Fetching Google Trends scores...")
    products = enrich_with_trend_score(products[:40])

    # 3. Score and rank
    for p in products:
        p["virality_score"] = score_product(p)
        p["estimated_margin"] = estimate_margin(p.get("cj_price"))

    products.sort(key=lambda x: x["virality_score"], reverse=True)
    top = products[:TOP_N]

    # 4. Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scanned": len(products),
        "products": top,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(top)} products to {OUTPUT_PATH}")
    logger.info("=== Done ===")


if __name__ == "__main__":
    run()
