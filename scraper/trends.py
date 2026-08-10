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


def discover_trending_keywords() -> list[str]:
    """
    DISCOVERY MODE — finds what's trending in the US today on Google,
    then filters for product-like terms. These become search queries
    for the CJ catalog to find sourceable products.
    """
    pytrends = TrendReq(hl="en-US", tz=360)
    keywords: list[str] = []

    try:
        # Daily trending searches in the US
        trending_df = pytrends.trending_searches(pn="united_states")
        raw = trending_df[0].tolist()

        # Keep terms that look like products (short, not a person's name, no news verbs)
        skip_words = {"dies", "dead", "killed", "arrested", "shooting", "crash", "vs", "election"}
        for term in raw:
            words = term.lower().split()
            if len(words) > 5:
                continue
            if any(w in skip_words for w in words):
                continue
            keywords.append(term)

        logger.info(f"Google Trends discovery: {len(keywords)} trending keywords")
    except Exception as e:
        logger.warning(f"Trending search discovery failed: {e}")

    # Also add rising queries from ecommerce seed categories
    try:
        pytrends2 = TrendReq(hl="en-US", tz=360)
        seeds = ECOMMERCE_CATEGORIES[:5]
        pytrends2.build_payload(seeds, timeframe="now 7-d", geo="US")
        related = pytrends2.related_queries()
        for kw in seeds:
            if kw in related:
                rising = related[kw].get("rising")
                if rising is not None and not rising.empty:
                    keywords.extend(rising["query"].head(5).tolist())
        time.sleep(1.5)
    except Exception as e:
        logger.warning(f"Rising query discovery failed: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique.append(kw)

    return unique[:30]


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
