"""
dba.dk tarayıcısı.

dba.dk Danimarka'nın popüler ikinci el ilan sitesidir ve giriş
gerektirmez. Arama sonuç sayfası requests + BeautifulSoup ile
taranabilir. dba.dk zaman zaman HTML yapısını değiştirdiği için
birden fazla seçici (selector) denenir.
"""

import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("price-compare.dba")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

SEARCH_URL = "https://www.dba.dk/soeg/"


def _parse_price(text):
    """'1.250 kr.' gibi metinden sayısal fiyatı çıkarır (DKK)."""
    if not text:
        return None
    # Danimarka formatı: nokta binlik ayracı, virgül ondalık
    cleaned = re.sub(r"[^\d.,]", "", text)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def scrape_dba(query, limit=5):
    """dba.dk üzerinde arama yapar ve ilan listesi döndürür."""
    params = {"soeg": query}
    listings = []
    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("dba.dk isteği başarısız: %s", exc)
        raise

    soup = BeautifulSoup(resp.text, "html.parser")

    # dba.dk kart yapısı için birkaç olası seçici denenir.
    cards = (
        soup.select("article")
        or soup.select("[class*='listing']")
        or soup.select("[class*='result']")
    )

    for card in cards:
        if len(listings) >= limit:
            break

        link_el = card.find("a", href=True)
        if not link_el:
            continue
        href = link_el["href"]
        if href.startswith("/"):
            href = "https://www.dba.dk" + href

        title_el = (
            card.find(["h2", "h3"])
            or card.find(attrs={"class": re.compile("title", re.I)})
            or link_el
        )
        title = title_el.get_text(strip=True) if title_el else ""

        price_el = card.find(string=re.compile(r"kr", re.I)) or card.find(
            attrs={"class": re.compile("price", re.I)}
        )
        price_text = ""
        if price_el:
            price_text = price_el if isinstance(price_el, str) else price_el.get_text(strip=True)
        price = _parse_price(price_text)

        img_el = card.find("img")
        image = ""
        if img_el:
            image = img_el.get("src") or img_el.get("data-src") or ""

        if not title:
            continue

        listings.append(
            {
                "title": title,
                "price": price,
                "currency": "DKK",
                "url": href,
                "image": image,
                "description": "",
            }
        )

    return listings
