"""
TikTok viral product signal via Google Trends Shopping category.
No API key required — detects what's going viral on TikTok by
finding spikes in US Shopping searches for TikTok-style products.
"""
import time
import logging
from pytrends.request import TrendReq

logger = logging.getLogger(__name__)

# Seed terms that surface TikTok-style viral product queries
TIKTOK_SEEDS = [
    "tiktok made me buy it",
    "viral gadget",
    "aesthetic room decor",
    "satisfying product",
    "cool kitchen tool",
]


def get_tiktok_signal_keywords() -> list[str]:
    """
    Returns rising product search terms surfaced by TikTok virality.
    Uses Google Trends Shopping category (gprop='froogle') to find
    what people are actively searching to BUY after seeing TikTok content.
    """
    pytrends = TrendReq(hl="en-US", tz=360)
    keywords: list[str] = []

    chunks = [TIKTOK_SEEDS[i:i+5] for i in range(0, len(TIKTOK_SEEDS), 5)]

    for chunk in chunks:
        try:
            pytrends.build_payload(chunk, timeframe="now 7-d", geo="US", gprop="froogle")
            related = pytrends.related_queries()

            for kw in chunk:
                if kw not in related:
                    continue
                rising = related[kw].get("rising")
                if rising is not None and not rising.empty:
                    keywords.extend(rising["query"].head(8).tolist())

            time.sleep(2)
        except Exception as e:
            logger.warning(f"TikTok signal fetch failed for {chunk}: {e}")
            time.sleep(5)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique.append(kw)

    logger.info(f"TikTok signal: {len(unique)} trending keywords found")
    return unique
