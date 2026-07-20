"""
Facebook Marketplace tarayıcısı.

Facebook Marketplace giriş gerektirir. Kullanıcı `fb_login.py` scriptini
bir kez çalıştırarak oturum çerezlerini `fb_cookies.json` dosyasına
kaydeder. Bu tarayıcı, kayıtlı çerezleri Playwright ile yükleyerek
Marketplace araması yapar.

Facebook, otomasyonu (bot) agresif şekilde tespit eder. Bu yüzden:
- Tarayıcı görünür (headful) modda açılır — bot tespitini azaltır.
- "AutomationControlled" bayrağı ve navigator.webdriver gizlenir.
- Güncel bir macOS Chrome user-agent'ı kullanılır.
- Sayfa yüklendikten sonra oturum hâlâ geçersizse (login sayfası veya
  login formu görünürse) uyarı verilir ve boş liste dönülür.

Çerez dosyası yoksa, Playwright yüklü değilse veya oturum geçersizse
hata fırlatmak yerine boş liste döndürülür ve durum loglanır (uygulama
akışı bozulmaz).
"""

import json
import logging
import os
import re

logger = logging.getLogger("price-compare.facebook")

COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "fb_cookies.json")
# Marketplace bölgesi. Kopenhag varsayılan; değiştirilebilir.
MARKETPLACE_LOCATION = os.environ.get("FB_MARKETPLACE_LOCATION", "copenhagen")
# Görünür tarayıcı varsayılan (bot tespitini azaltır). Ekran yoksa (sunucu)
# FB_HEADLESS=1 ile headless moda geçilebilir.
HEADLESS = os.environ.get("FB_HEADLESS", "0") == "1"

# Güncel macOS Chrome user-agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Bot tespitini azaltan tarayıcı argümanları.
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-notifications",
    "--start-maximized",
    "--disable-features=IsolateOrigins,site-per-process",
]

# navigator.webdriver vb. otomasyon izlerini gizleyen init script.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['da-DK', 'da', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || { runtime: {} };
"""


def _parse_price(text):
    """Fiyat metninden sayı ve para birimini çıkarır."""
    if not text:
        return None, "DKK"
    lowered = text.lower()
    currency = "DKK"
    if "kr" in lowered:
        currency = "DKK"
    elif "€" in text or "eur" in lowered:
        currency = "EUR"
    elif "$" in text or "usd" in lowered:
        currency = "USD"
    elif "₺" in text or "tl" in lowered:
        currency = "TRY"

    digits = re.sub(r"[^\d.,]", "", text)
    digits = digits.replace(".", "").replace(",", ".")
    try:
        return (float(digits) if digits else None), currency
    except ValueError:
        return None, currency


def _looks_like_login(page):
    """Sayfa oturum açma gerektiriyor mu (çerezler geçersiz mi) kontrol eder."""
    try:
        url = (page.url or "").lower()
        if "login" in url or "/checkpoint" in url:
            return True
        # Giriş formu alanları görünüyorsa oturum yok demektir.
        if page.query_selector("input[name='email']") and page.query_selector(
            "input[name='pass']"
        ):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _extract_text(handle):
    """Bir element handle'ından güvenli şekilde metin alır."""
    try:
        return (handle.inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _pick_title_price(lines):
    """Bir ilan bloğundaki satırlardan başlık ve fiyatı ayıklar."""
    lines = [l.strip() for l in lines if l and l.strip()]
    # Fiyat satırı: içinde para birimi işareti veya rakam+kr/tl olan ilk satır.
    price_line = ""
    for l in lines:
        if re.search(r"(kr|tl|₺|€|\$)", l, re.I) and re.search(r"\d", l):
            price_line = l
            break
    if not price_line:
        price_line = next((l for l in lines if re.search(r"\d", l)), "")

    price, currency = _parse_price(price_line)
    # Başlık: fiyat dışındaki en uzun anlamlı satır.
    candidates = [l for l in lines if l != price_line and len(l) > 2]
    title = max(candidates, key=len) if candidates else (lines[0] if lines else "")
    return title, price, currency


def _collect_from_item_links(page, limit):
    """Strateji A: /marketplace/item/ linklerinden ilan topla."""
    listings = []
    seen = set()
    anchors = page.query_selector_all("a[href*='/marketplace/item/']")
    for a in anchors:
        if len(listings) >= limit:
            break
        href = a.get_attribute("href") or ""
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        item_id = href.split("/marketplace/item/")[-1].split("/")[0].split("?")[0]
        if not item_id or item_id in seen:
            continue

        # İlan metnini önce link'in kendisinden, yoksa üst kapsayıcıdan al.
        text = _extract_text(a)
        if len(text.split("\n")) < 2:
            try:
                parent = a.evaluate_handle(
                    "el => el.closest('[role=\"article\"]') || el.parentElement"
                )
                parent_text = _extract_text(parent.as_element()) if parent else ""
                if len(parent_text) > len(text):
                    text = parent_text
            except Exception:  # noqa: BLE001
                pass

        lines = text.split("\n")
        title, price, currency = _pick_title_price(lines)
        if not title:
            # aria-label bazen başlığı taşır.
            aria = a.get_attribute("aria-label") or ""
            if aria:
                title = aria.strip()
        if not title:
            continue

        seen.add(item_id)
        img_el = a.query_selector("img")
        image = ""
        if img_el:
            image = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

        listings.append(
            {
                "title": title[:200],
                "price": price,
                "currency": currency,
                "url": href,
                "image": image or "",
                "description": "",
            }
        )
    return listings


def _collect_from_main_links(page, limit):
    """Strateji B: [role='main'] içindeki marketplace linklerinden ilan topla.

    /marketplace/item/ linkleri bulunamazsa daha geniş bir arama yapar.
    """
    listings = []
    seen = set()
    anchors = page.query_selector_all("[role='main'] a[href*='marketplace']")
    for a in anchors:
        if len(listings) >= limit:
            break
        href = a.get_attribute("href") or ""
        if not href or "marketplace" not in href:
            continue
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        key = href.split("?")[0]
        # Yalnızca ilan (item) linklerini al; kategori/menü linklerini ele.
        if "/marketplace/item/" not in key:
            continue
        if key in seen:
            continue
        seen.add(key)

        text = _extract_text(a)
        lines = text.split("\n")
        title, price, currency = _pick_title_price(lines)
        if not title:
            title = (a.get_attribute("aria-label") or "").strip()
        if not title:
            continue

        img_el = a.query_selector("img")
        image = img_el.get_attribute("src") if img_el else ""
        listings.append(
            {
                "title": title[:200],
                "price": price,
                "currency": currency,
                "url": href,
                "image": image or "",
                "description": "",
            }
        )
    return listings


def _collect_from_aria_links(page, limit):
    """Strateji C: aria-label taşıyan link elementlerinden ilan topla."""
    listings = []
    seen = set()
    anchors = page.query_selector_all("a[aria-label][href*='/marketplace/']")
    for a in anchors:
        if len(listings) >= limit:
            break
        href = a.get_attribute("href") or ""
        aria = (a.get_attribute("aria-label") or "").strip()
        if not href or not aria:
            continue
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        key = href.split("?")[0]
        if key in seen:
            continue
        seen.add(key)

        # aria-label genellikle "Başlık - Fiyat kr" biçimindedir.
        price, currency = _parse_price(aria)
        title = re.split(r"\d[\d.,]*\s*(kr|tl|€|\$|₺)", aria, flags=re.I)[0].strip(" -–—")
        if not title:
            title = aria
        img_el = a.query_selector("img")
        image = img_el.get_attribute("src") if img_el else ""
        listings.append(
            {
                "title": title[:200],
                "price": price,
                "currency": currency,
                "url": href,
                "image": image or "",
                "description": "",
            }
        )
    return listings


def scrape_facebook(query, limit=5):
    """Facebook Marketplace üzerinde arama yapar."""
    if not os.path.exists(COOKIES_FILE):
        logger.warning(
            "FB çerez dosyası bulunamadı (%s). Önce `python fb_login.py` "
            "çalıştırarak Facebook oturumunuzu kurun.",
            COOKIES_FILE,
        )
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "Playwright yüklü değil. Kurulum: `pip install playwright && "
            "playwright install chromium`"
        )
        return []

    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as fh:
            cookies = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("FB çerez dosyası okunamadı (%s): %s", COOKIES_FILE, exc)
        return []

    if not any(c.get("name") == "c_user" for c in cookies):
        logger.warning(
            "Facebook oturumu geçersiz görünüyor. Tekrar fb_login.py çalıştırın."
        )
        return []

    listings = []
    search_url = (
        f"https://www.facebook.com/marketplace/{MARKETPLACE_LOCATION}/search/"
        f"?query={query}&exact=false"
    )

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Görünür tarayıcı başlatılamadı (%s). Ekran yoksa "
                "FB_HEADLESS=1 ile headless deneyin.",
                exc,
            )
            return []

        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="da-DK",
            viewport={"width": 1366, "height": 900},
            bypass_csp=True,
        )
        try:
            context.add_init_script(STEALTH_JS)
        except Exception:  # noqa: BLE001
            pass

        try:
            context.add_cookies(cookies)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FB çerezleri yüklenemedi: %s", exc)
            browser.close()
            return []

        page = context.new_page()
        try:
            page.goto(search_url, timeout=60000, wait_until="domcontentloaded")

            # Çerez/onay diyaloglarını kapatmaya çalış (varsa).
            try:
                page.wait_for_timeout(1500)
                for label in ["Tümünü kabul et", "Allow all cookies", "Accept all"]:
                    btn = page.query_selector(f"[aria-label='{label}']")
                    if btn:
                        btn.click()
                        break
            except Exception:  # noqa: BLE001
                pass

            # Oturum geçerli mi?
            if _looks_like_login(page):
                logger.warning(
                    "Facebook oturumu geçersiz veya süresi dolmuş (login "
                    "sayfasına yönlendirildi). `python fb_login.py` ile "
                    "yeniden giriş yapın."
                )
                browser.close()
                return []

            # İlan linklerinin belirmesini bekle (uzun timeout).
            try:
                page.wait_for_selector(
                    "a[href*='/marketplace/item/']", timeout=25000
                )
            except Exception:  # noqa: BLE001
                logger.info(
                    "İlan linkleri belirmedi; yine de mevcut içerik taranacak."
                )

            # Daha fazla sonuç yüklemek için kademeli scroll (3 kez, 2 sn bekle).
            for _ in range(3):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(2000)

            # Strateji A: /marketplace/item/ linkleri.
            listings = _collect_from_item_links(page, limit)

            # Strateji B: yetersizse [role='main'] içindeki marketplace linkleri.
            if len(listings) < limit:
                extra = _collect_from_main_links(page, limit - len(listings))
                seen_urls = {l["url"] for l in listings}
                for item in extra:
                    if item["url"] not in seen_urls:
                        listings.append(item)
                        seen_urls.add(item["url"])

            # Strateji C: hâlâ yetersizse aria-label'lı linkler.
            if len(listings) < limit:
                extra = _collect_from_aria_links(page, limit - len(listings))
                seen_urls = {l["url"] for l in listings}
                for item in extra:
                    if item["url"] not in seen_urls:
                        listings.append(item)
                        seen_urls.add(item["url"])

            if not listings:
                logger.info(
                    "Facebook Marketplace'te '%s' için sonuç bulunamadı "
                    "(selector değişmiş olabilir veya sonuç yok).",
                    query,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("FB Marketplace taranırken hata: %s", exc)
        finally:
            browser.close()

    return listings
