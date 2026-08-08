import re
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
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

# Category slug → human label
CATEGORIES = {
    "": "All Departments",
    "kitchen": "Kitchen",
    "beauty": "Beauty",
    "electronics": "Electronics",
    "sports": "Sports & Outdoors",
    "toys-and-games": "Toys & Games",
    "home-garden": "Home & Garden",
    "pet-supplies": "Pet Supplies",
    "automotive": "Automotive",
}


def scrape_movers_and_shakers(category: str = "") -> list[dict]:
    """
    Scrape Amazon Movers & Shakers for a given category slug.
    Returns list of dicts: {name, category, rank_change_pct, asin, url}
    """
    base = "https://www.amazon.com/gp/movers-and-shakers"
    url = f"{base}/{category}" if category else base

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Amazon fetch failed [{category}]: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    products = []

    # Amazon wraps each M&S item in a div with a data-asin attribute
    items = soup.select("div[data-asin]")

    for item in items[:20]:
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        name_el = item.select_one("span.zg-text-center-align a, .p13n-sc-truncated, a.a-link-normal span")
        if not name_el:
            name_el = item.select_one("a .a-size-small, a .a-truncate-full, .a-size-medium")
        name = name_el.get_text(strip=True) if name_el else ""

        if not name:
            continue

        # Rank change: "2,415%" or similar
        rank_el = item.select_one(".zg-badge-text, .badge-text")
        rank_change_pct = 0
        if rank_el:
            raw = rank_el.get_text(strip=True).replace(",", "").replace("%", "").replace("+", "")
            try:
                rank_change_pct = int(re.sub(r"[^\d]", "", raw) or 0)
            except ValueError:
                pass

        products.append(
            {
                "name": name,
                "category": CATEGORIES.get(category, category),
                "rank_change_pct": rank_change_pct,
                "asin": asin,
                "url": f"https://www.amazon.com/dp/{asin}",
                "source": "amazon_movers",
            }
        )

    return products


def get_all_movers(limit_per_category: int = 10) -> list[dict]:
    """
    Pull Movers & Shakers across all tracked categories.
    Deduplicates by ASIN.
    """
    seen_asins: set[str] = set()
    all_products: list[dict] = []

    for slug, label in CATEGORIES.items():
        logger.info(f"Scraping Amazon M&S: {label}")
        items = scrape_movers_and_shakers(slug)

        for item in items[:limit_per_category]:
            if item["asin"] not in seen_asins:
                seen_asins.add(item["asin"])
                all_products.append(item)

        time.sleep(2)  # polite delay between category requests

    # Sort by rank change descending (highest momentum first)
    all_products.sort(key=lambda x: x["rank_change_pct"], reverse=True)
    return all_products
