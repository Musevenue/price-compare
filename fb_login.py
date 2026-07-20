"""
Facebook oturum kurulum scripti.

Bu scripti BİR KEZ çalıştırın. Görünür (headful) bir Chromium penceresi
açılır; Facebook hesabınıza normal şekilde giriş yapın. Giriş
tamamlandıktan sonra terminale dönüp ENTER'a basın. Oturum çerezleri
`fb_cookies.json` dosyasına kaydedilir ve sonraki taramalarda otomatik
kullanılır.

Kullanım:
    python fb_login.py

Not: Playwright ilk kullanımdan önce tarayıcı indirmelidir:
    pip install playwright
    playwright install chromium
"""

import json
import os
import sys

COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "fb_cookies.json")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright yüklü değil. Kurulum: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("=" * 60)
    print("Facebook oturum kurulumu başlatılıyor...")
    print("Açılan pencerede Facebook hesabınıza giriş yapın.")
    print("Giriş tamamlanınca bu terminale dönüp ENTER'a basın.")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="da-DK")
        page = context.new_page()
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        input("\nGiriş yaptıktan sonra ENTER'a basın... ")

        cookies = context.cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as fh:
            json.dump(cookies, fh, ensure_ascii=False, indent=2)

        print(f"\n✓ {len(cookies)} çerez '{COOKIES_FILE}' dosyasına kaydedildi.")
        print("Artık uygulamayı çalıştırabilirsiniz: python app.py")
        browser.close()


if __name__ == "__main__":
    main()
