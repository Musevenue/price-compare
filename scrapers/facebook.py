"""
Facebook Marketplace tarayıcısı.

Facebook Marketplace giriş gerektirir. Kullanıcı `fb_login.py` scriptini
bir kez çalıştırarak oturum çerezlerini `fb_cookies.json` dosyasına
kaydeder. Bu tarayıcı, kayıtlı çerezleri Playwright ile yükleyerek
Marketplace araması yapar.

Çerez dosyası yoksa veya Playwright yüklü değilse, hata fırlatmak
yerine boş liste döndürülür ve durum loglanır (uygulama akışı bozulmaz).
"""

import json
import logging
import os
import re

logger = logging.getLogger("price-compare.facebook")

COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "fb_cookies.json")
# Marketplace bölgesi. Kopenhag varsayılan; değiştirilebilir.
MARKETPLACE_LOCATION = os.environ.get("FB_MARKETPLACE_LOCATION", "copenhagen")


def _parse_price(text):
    """Fiyat metninden sayı ve para birimini çıkarır."""
    if not text:
        return None, "DKK"
    currency = "DKK"
    if "kr" in text.lower():
        currency = "DKK"
    elif "€" in text or "eur" in text.lower():
        currency = "EUR"
    elif "$" in text or "usd" in text.lower():
        currency = "USD"
    elif "₺" in text or "tl" in text.lower():
        currency = "TRY"

    digits = re.sub(r"[^\d.,]", "", text)
    digits = digits.replace(".", "").replace(",", ".")
    try:
        return (float(digits) if digits else None), currency
    except ValueError:
        return None, currency


def scrape_facebook(query, limit=5):
    """Facebook Marketplace üzerinde arama yapar."""
    if not os.path.exists(COOKIES_FILE):
        logger.warning(
            "FB çerez dosyası bulunamadı (%s). Önce `python fb_login.py` çalıştırın.",
            COOKIES_FILE,
        )
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright yüklü değil. `pip install playwright` çalıştırın.")
        return []

    with open(COOKIES_FILE, "r", encoding="utf-8") as fh:
        cookies = json.load(fh)

    listings = []
    search_url = (
        f"https://www.facebook.com/marketplace/{MARKETPLACE_LOCATION}/search/"
        f"?query={query}"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="da-DK",
        )
        try:
            context.add_cookies(cookies)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FB çerezleri yüklenemedi: %s", exc)
            browser.close()
            return []

        page = context.new_page()
        try:
            page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            # Marketplace ilanları /marketplace/item/ linkleri ile gelir.
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(2000)

            anchors = page.query_selector_all("a[href*='/marketplace/item/']")
            seen = set()
            for a in anchors:
                if len(listings) >= limit:
                    break
                href = a.get_attribute("href") or ""
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://www.facebook.com" + href
                item_id = href.split("/marketplace/item/")[-1].split("/")[0]
                if item_id in seen:
                    continue
                seen.add(item_id)

                text = a.inner_text().strip()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                price_line = next((l for l in lines if re.search(r"\d", l)), "")
                price, currency = _parse_price(price_line)
                # Başlık genellikle fiyattan sonraki en uzun satırdır.
                title_candidates = [l for l in lines if l != price_line]
                title = max(title_candidates, key=len) if title_candidates else text

                img_el = a.query_selector("img")
                image = img_el.get_attribute("src") if img_el else ""

                listings.append(
                    {
                        "title": title,
                        "price": price,
                        "currency": currency,
                        "url": href,
                        "image": image or "",
                        "description": "",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("FB Marketplace taranırken hata: %s", exc)
        finally:
            browser.close()

    return listings
