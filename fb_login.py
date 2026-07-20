"""
Facebook oturum kurulum scripti.

Bu scripti BİR KEZ çalıştırın. Görünür (headful) bir Chromium penceresi
açılır; Facebook hesabınıza normal şekilde giriş yapın. Giriş
tamamlandıktan sonra script sizi Marketplace sayfasına götürür (tüm
oturum çerezleri tam yüklensin diye), ardından terminale dönüp ENTER'a
basmanız istenir. Oturum çerezleri `fb_cookies.json` dosyasına
kaydedilir ve sonraki taramalarda otomatik kullanılır.

Kullanım:
    python fb_login.py

Not: Playwright ilk kullanımdan önce tarayıcı indirmelidir:
    pip install playwright
    playwright install chromium

Görünür pencere açılamıyorsa (ör. ekranı olmayan sunucu, "no display"
hatası), script bunu yakalar ve size çerezleri elle içe aktarma
(manuel import) seçeneğini anlatır.
"""

import json
import os
import sys

COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "fb_cookies.json")

# Güncel macOS Chrome user-agent (scraper ile tutarlı).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--start-maximized",
]


def _manual_import_help():
    """Görünür pencere açılamazsa elle çerez içe aktarma yönergesi verir."""
    print("\n" + "!" * 64)
    print("Görünür tarayıcı penceresi açılamadı.")
    print("Bu genellikle ekranı olmayan bir ortamda (sunucu / SSH) olur.")
    print("Bu script macOS gibi masaüstü bir ortamda çalıştırılmalıdır.")
    print("-" * 64)
    print("ALTERNATİF — çerezleri elle içe aktarma:")
    print("1. Kendi bilgisayarınızın Chrome tarayıcısında Facebook'a girin.")
    print("2. 'Cookie-Editor' gibi bir eklenti ile çerezleri JSON olarak")
    print("   dışa aktarın (Export -> JSON).")
    print(f"3. Bu JSON'u proje klasöründe '{COOKIES_FILE}' olarak kaydedin.")
    print("4. JSON, Playwright biçiminde bir liste olmalı; her çerez en az")
    print("   'name', 'value', 'domain', 'path' alanlarını içermeli ve")
    print("   içinde 'c_user' çerezi bulunmalıdır.")
    print("!" * 64)


def _validate_cookies(cookies):
    """Çerez listesini doğrular; (geçerli_mi, mesaj) döndürür."""
    if not isinstance(cookies, list) or not cookies:
        return False, "Çerez listesi boş."
    has_c_user = any(c.get("name") == "c_user" for c in cookies)
    has_xs = any(c.get("name") == "xs" for c in cookies)
    if not has_c_user:
        return False, (
            "'c_user' çerezi bulunamadı — giriş yapılmamış görünüyor. "
            "Facebook'a giriş yapıp tekrar deneyin."
        )
    if not has_xs:
        return True, (
            "UYARI: 'xs' çerezi yok. Oturum eksik olabilir; sorun yaşarsanız "
            "yeniden giriş yapın."
        )
    return True, "Oturum çerezleri geçerli görünüyor (c_user + xs mevcut)."


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright yüklü değil. Kurulum:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
        sys.exit(1)

    print("=" * 64)
    print("Facebook oturum kurulumu başlatılıyor...")
    print("Açılan pencerede Facebook hesabınıza giriş yapın.")
    print("Giriş yaptıktan sonra script sizi Marketplace'e götürecek.")
    print("=" * 64)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, args=BROWSER_ARGS)
        except Exception as exc:  # noqa: BLE001
            print(f"\nTarayıcı başlatılamadı: {exc}")
            _manual_import_help()
            sys.exit(1)

        context = browser.new_context(user_agent=USER_AGENT, locale="da-DK")
        page = context.new_page()

        try:
            page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            print(f"\nFacebook açılamadı: {exc}")
            browser.close()
            _manual_import_help()
            sys.exit(1)

        input("\n>>> Facebook'a giriş yaptıktan sonra ENTER'a basın... ")

        # Oturum çerezlerinin tam yüklenmesi için Marketplace'e git.
        print("Marketplace sayfasına gidiliyor (çerezler tamamlanıyor)...")
        try:
            page.goto(
                "https://www.facebook.com/marketplace/",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            page.wait_for_timeout(4000)
        except Exception as exc:  # noqa: BLE001
            print(f"Marketplace açılırken uyarı (yok sayılabilir): {exc}")

        cookies = context.cookies()
        browser.close()

    valid, message = _validate_cookies(cookies)
    if not valid:
        print(f"\n✗ {message}")
        print("Çerezler KAYDEDİLMEDİ. Lütfen giriş yapıp tekrar deneyin.")
        sys.exit(1)

    with open(COOKIES_FILE, "w", encoding="utf-8") as fh:
        json.dump(cookies, fh, ensure_ascii=False, indent=2)

    print(f"\n✓ {len(cookies)} çerez '{COOKIES_FILE}' dosyasına kaydedildi.")
    print(f"✓ {message}")
    print("\nArtık uygulamayı çalıştırabilirsiniz: python app.py")


if __name__ == "__main__":
    main()
