import time
import logging
from pytrends.request import TrendReq

logger = logging.getLogger(__name__)

ECOMMERCE_CATEGORIES = [
    "home decor",
    "kitchen gadgets",
    "fitness equipment",
    "pet supplies",
    "phone accessories",
    "beauty tools",
    "car accessories",
    "outdoor gear",
    "baby products",
    "office supplies",
]


def get_rising_searches(categories: list[str] = None) -> dict[str, int]:
    """
    Returns a dict of {keyword: interest_score (0-100)} for rising searches
    across e-commerce relevant categories.
    """
    if categories is None:
        categories = ECOMMERCE_CATEGORIES

    pytrends = TrendReq(hl="en-US", tz=360)
    results: dict[str, int] = {}

    # pytrends accepts max 5 keywords per request
    chunks = [categories[i : i + 5] for i in range(0, len(categories), 5)]

    for chunk in chunks:
        try:
            pytrends.build_payload(chunk, timeframe="now 7-d", geo="US")
            data = pytrends.interest_over_time()

            if data.empty:
                continue

            # Average interest over the last 7 days for each keyword
            for kw in chunk:
                if kw in data.columns:
                    avg = int(data[kw].mean())
                    if avg > 0:
                        results[kw] = avg

            time.sleep(1.5)  # stay under rate limit
        except Exception as e:
            logger.warning(f"Trends fetch failed for chunk {chunk}: {e}")
            time.sleep(5)

    return results


def enrich_with_trend_score(products: list[dict]) -> list[dict]:
    """
    Given a list of products with a 'name' field, look up each product's
    Google Trends score and attach it as 'trend_score'.
    """
    if not products:
        return products

    pytrends = TrendReq(hl="en-US", tz=360)
    names = [p["name"][:100] for p in products]
    chunks = [names[i : i + 5] for i in range(0, len(names), 5)]

    score_map: dict[str, int] = {}

    for chunk in chunks:
        try:
            pytrends.build_payload(chunk, timeframe="now 7-d", geo="US")
            data = pytrends.interest_over_time()

            if not data.empty:
                for kw in chunk:
                    if kw in data.columns:
                        score_map[kw] = int(data[kw].mean())

            time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Trend enrichment failed for {chunk}: {e}")
            time.sleep(5)

    for p in products:
        p["trend_score"] = score_map.get(p["name"][:100], 0)

    return products
