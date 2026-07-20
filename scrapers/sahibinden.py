"""
Sahibinden.com tarayıcısı.

Sahibinden.com Türkiye'nin en büyük ilan sitesidir. Fiyatlar TRY
cinsindedir ve DKK'ya çevrilir. Site bot korumasına sahip olduğu için
Playwright (görünür/headful) ile gerçek tarayıcı benzeri istekler
kullanılır ve sayfanın yüklenmesi için yeterince beklenir.

Playwright yüklü değilse veya sayfa engellenirse boş liste döndürülür.
"""

import logging
import re

logger = logging.getLogger("price-compare.sahibinden")

SEARCH_URL = "https://www.sahibinden.com/arama"

# Sonuç satırları için denenecek selector'lar (sırayla).
ROW_SELECTORS = [
    "tr.searchResultsItem",
    "table.search-result-list tr",
    ".classified-list li",
    "tr[data-id]",
]

# Başlık linki için denenecek selector'lar.
TITLE_SELECTORS = [
    "a.classifiedTitle",
    "a[href*='/ilan/']",
    ".classifiedTitle a",
    "a",
]

# Fiyat hücresi için denenecek selector'lar.
PRICE_SELECTORS = [
    "td.searchResultsPriceValue",
    ".searchResultsPriceValue",
    ".classified-price-container",
    "[class*='price']",
]


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


def _first_matching_rows(page):
    """İlan satırlarını, çalışan ilk selector ile döndürür."""
    for sel in ROW_SELECTORS:
        try:
            rows = page.query_selector_all(sel)
        except Exception:  # noqa: BLE001
            rows = []
        if rows:
            logger.info("Sahibinden: '%s' selector'ı ile %d satır bulundu", sel, len(rows))
            return rows
    return []


def _query_first(row, selectors):
    """Bir satırda verilen selector'lardan ilk eşleşen elementi döndürür."""
    for sel in selectors:
        try:
            el = row.query_selector(sel)
        except Exception:  # noqa: BLE001
            el = None
        if el:
            return el
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
        try:
            browser = p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sahibinden için tarayıcı başlatılamadı: %s", exc)
            return []

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
                f"{SEARCH_URL}?query_text={query}&pagingSize=20",
                timeout=45000,
                wait_until="domcontentloaded",
            )
            # Sayfanın (ve olası JS içeriğin) yüklenmesi için bekle.
            page.wait_for_timeout(6000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:  # noqa: BLE001
                # networkidle'a ulaşılamazsa yine de devam et.
                pass

            rows = _first_matching_rows(page)
            for row in rows:
                if len(listings) >= limit:
                    break

                link_el = _query_first(row, TITLE_SELECTORS)
                if not link_el:
                    continue
                title = (link_el.inner_text() or "").strip()
                href = link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.sahibinden.com" + href

                price_el = _query_first(row, PRICE_SELECTORS)
                price_text = price_el.inner_text().strip() if price_el else ""
                price = _parse_price(price_text)

                # Başlık veya fiyat yoksa bu satırı atla.
                if not title or price is None:
                    continue

                img_el = row.query_selector("img")
                image = ""
                if img_el:
                    image = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

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

            if not listings:
                logger.info(
                    "Sahibinden.com'da '%s' için sonuç bulunamadı "
                    "(selector değişmiş olabilir veya bot engeli).",
                    query,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sahibinden.com taranırken hata: %s", exc)
        finally:
            browser.close()

    return listings
