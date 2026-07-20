"""
Sahibinden.com tarayıcısı.

Sahibinden.com Türkiye'nin en büyük ilan sitesidir. Fiyatlar TRY
cinsindedir ve DKK'ya çevrilir. Site bot korumasına sahip olduğu için
Playwright (headless) ile gerçek tarayıcı benzeri istekler kullanılır.

Playwright yüklü değilse veya sayfa engellenirse boş liste döndürülür.
"""

import logging
import re

logger = logging.getLogger("price-compare.sahibinden")

SEARCH_URL = "https://www.sahibinden.com/kelime-ile-arama"


def _parse_price(text):
    """'1.250 TL' gibi metinden sayısal TRY fiyatını çıkarır."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text)
    # Türkçe format: nokta binlik, virgül ondalık
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def scrape_sahibinden(query, limit=5):
    """Sahibinden.com üzerinde arama yapar."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright yüklü değil. `pip install playwright` çalıştırın.")
        return []

    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="tr-TR",
        )
        page = context.new_page()
        try:
            page.goto(
                f"{SEARCH_URL}?query_text_mf={query}&query_text={query}",
                timeout=45000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(4000)

            rows = page.query_selector_all("tr.searchResultsItem")
            for row in rows:
                if len(listings) >= limit:
                    break
                link_el = row.query_selector("a.classifiedTitle")
                if not link_el:
                    continue
                title = (link_el.inner_text() or "").strip()
                href = link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.sahibinden.com" + href

                price_el = row.query_selector("td.searchResultsPriceValue")
                price_text = price_el.inner_text().strip() if price_el else ""
                price = _parse_price(price_text)

                img_el = row.query_selector("img")
                image = ""
                if img_el:
                    image = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                if not title:
                    continue

                listings.append(
                    {
                        "title": title,
                        "price": price,
                        "currency": "TRY",
                        "url": href,
                        "image": image,
                        "description": "",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sahibinden.com taranırken hata: %s", exc)
        finally:
            browser.close()

    return listings
