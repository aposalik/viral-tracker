"""
Viral Product Tracker — main orchestrator
Run: python scraper/main.py
Output: public/products.json
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from amazon import get_all_movers
from cj import enrich_with_cj
from trends import enrich_with_trend_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent.parent / "public" / "products.json"
TOP_N = 25  # how many products to keep in the final output


def score_product(p: dict) -> float:
    """
    Composite virality score (0-200):
      - Amazon momentum:  rank_change_pct mapped to 0-100 (capped at 5000%)
      - Google Trends:    trend_score 0-100 as-is
    """
    amazon_score = min(p.get("rank_change_pct", 0) / 50, 100)
    trend_score = p.get("trend_score", 0)
    return round(amazon_score + trend_score, 1)


def estimate_margin(cj_price: float | None) -> str:
    """
    Rough margin estimate assuming 2.5-3x CJ price as retail.
    Returns a label like '35-45%' or 'N/A'.
    """
    if not cj_price or cj_price <= 0:
        return "N/A"

    retail_low = cj_price * 2.5
    retail_high = cj_price * 3.0

    # Deduct platform (10%) + payment (3%) + ads (15%) + shipping buffer
    costs_low = cj_price + retail_low * 0.28
    costs_high = cj_price + retail_high * 0.28

    margin_low = max(0, (retail_low - costs_low) / retail_low * 100)
    margin_high = max(0, (retail_high - costs_high) / retail_high * 100)

    return f"{int(margin_low)}-{int(margin_high)}%"


def run():
    logger.info("=== Viral Product Tracker starting ===")

    # 1. Pull Amazon Movers & Shakers
    logger.info("Fetching Amazon Movers & Shakers...")
    products = get_all_movers(limit_per_category=8)
    logger.info(f"Got {len(products)} products from Amazon")

    if not products:
        logger.error("No products fetched — aborting")
        return

    # 2. Enrich with Google Trends scores
    logger.info("Fetching Google Trends scores...")
    products = enrich_with_trend_score(products)

    # 3. Enrich with CJ Dropshipping supplier data
    logger.info("Fetching CJ Dropshipping data...")
    products = enrich_with_cj(products)

    # 4. Score and rank
    for p in products:
        p["virality_score"] = score_product(p)
        p["estimated_margin"] = estimate_margin(p.get("cj_price"))

    products.sort(key=lambda x: x["virality_score"], reverse=True)
    top = products[:TOP_N]

    # 5. Write output
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
