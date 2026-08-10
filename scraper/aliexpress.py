"""
AliExpress bestselling product discovery.
Scrapes AliExpress public bestsellers page — no API key needed.
Falls back gracefully if blocked.
"""
import time
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Referer": "https://www.aliexpress.com/",
}

# Search terms that surface bestselling dropship-friendly products on AliExpress
BESTSELLER_QUERIES = [
    "home gadget bestseller",
    "kitchen tool trending",
    "beauty device popular",
    "pet toy bestseller",
    "phone accessory viral",
]


def get_aliexpress_bestsellers() -> list[str]:
    """
    Returns a list of product names from AliExpress trending/bestseller searches.
    Uses their search page sorted by orders (most sold).
    Returns empty list if blocked — caller handles gracefully.
    """
    product_names: list[str] = []

    for query in BESTSELLER_QUERIES:
        try:
            resp = requests.get(
                "https://www.aliexpress.com/wholesale",
                params={
                    "SearchText": query,
                    "SortType": "total_tranpro_desc",
                    "page": 1,
                },
                headers=HEADERS,
                timeout=15,
            )

            if resp.status_code != 200:
                logger.warning(f"AliExpress returned {resp.status_code} for '{query}'")
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # AliExpress product titles are in <h1> or <a> tags with product info
            titles = soup.select("h1[class*='title'], a[class*='title'], span[class*='title--']")

            for el in titles[:5]:
                name = el.get_text(strip=True)
                if name and len(name) > 5 and len(name) < 120:
                    product_names.append(name)

            time.sleep(2)

        except Exception as e:
            logger.warning(f"AliExpress fetch failed for '{query}': {e}")
            time.sleep(3)

    unique = list(dict.fromkeys(product_names))
    logger.info(f"AliExpress: {len(unique)} product names found")
    return unique
