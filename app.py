"""
Fiyat Karşılaştırma Uygulaması (price-compare)
-----------------------------------------------
dba.dk, Facebook Marketplace ve Sahibinden.com platformlarından
ürün ilanlarını tarar, fiyatları DKK'ya çevirir, akıllı filtre uygular
ve Ollama ile metin + (destekliyse) görsel analizi üretir.

Yerel (localhost) çalışacak şekilde tasarlanmıştır.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request

# .env dosyasını yükle (varsa)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from scrapers.dba import scrape_dba
from scrapers.facebook import scrape_facebook
from utils.currency import to_dkk
from utils.filter import filter_listings, relevance_score
from utils.ollama_client import analyze_image, summarize_listing, _ensure_ready, _state as ollama_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("price-compare")

app = Flask(__name__)

# Platform tarayıcı eşlemesi. Her fonksiyon (query, limit) alır ve
# ilan sözlüklerinden oluşan bir liste döndürür.
PLATFORMS = {
    "dba.dk": scrape_dba,
    "Facebook Marketplace": scrape_facebook,
}

# Kullanıcı limiti ne olursa olsun önce geniş örneklem çek.
SCRAPER_LIMIT = 25


def _run_scraper(name, func, query, limit):
    """Tek bir platformu tarar, hataları zarifçe ele alır."""
    try:
        listings = func(query, limit=limit) or []
        logger.info("%s: %d ilan bulundu", name, len(listings))
        return name, listings, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s taranırken hata: %s", name, exc)
        return name, [], str(exc)


def _parse_float_or_none(value):
    """Form değerini float'a çevirir; geçersizse None döndürür."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _title_relevance(title, query):
    """Başlıkta sorgu terimlerinden en az biri geçiyor mu?"""
    terms = re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", (query or "").lower(), flags=re.UNICODE)
    terms = [t for t in terms if len(t) >= 2]
    if not terms:
        return True
    t = (title or "").lower()
    return any(term in t for term in terms)


def _enrich_listing(listing, query):
    """İlanı DKK fiyatı, alaka skoru, metin özeti ve görsel analiz ile zenginleştirir."""
    price = listing.get("price")
    currency = listing.get("currency", "DKK")
    price_dkk = None
    if price is not None:
        try:
            price_dkk = to_dkk(price, currency)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fiyat dönüştürülemedi (%s %s): %s", price, currency, exc)
    listing["price_dkk"] = price_dkk

    listing["relevance_score"] = relevance_score(listing, query)
    listing["title_relevant"] = _title_relevance(listing.get("title"), query)

    # Metin özeti
    text_parts = [listing.get("title", ""), listing.get("description", "")]
    text = " ".join(p for p in text_parts if p).strip()
    listing["summary"] = summarize_listing(text) if text else ""

    # Görsel analizi (model desteklemiyorsa analyze_image boş döner ve devre dışı kalır)
    listing["image_analysis"] = analyze_image(listing.get("image"), listing.get("title", ""))
    return listing


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["GET", "POST"])
def search():
    query = (request.values.get("query") or "").strip()

    try:
        user_limit = int(request.values.get("limit", 5))
    except (TypeError, ValueError):
        user_limit = 5
    user_limit = max(1, min(user_limit, 20))

    min_price_dkk = _parse_float_or_none(request.values.get("min_price"))
    max_price_dkk = _parse_float_or_none(request.values.get("max_price"))

    if min_price_dkk is not None and max_price_dkk is not None and min_price_dkk > max_price_dkk:
        min_price_dkk, max_price_dkk = max_price_dkk, min_price_dkk

    if not query:
        return render_template("index.html", error="Lütfen bir ürün adı girin.")

    logger.info(
        "Arama başlatıldı: '%s' (gösterim limiti=%d, tarama limiti=%d, min=%s, max=%s)",
        query,
        user_limit,
        SCRAPER_LIMIT,
        min_price_dkk,
        max_price_dkk,
    )

    results = {}
    errors = {}

    # Platform taramalarını eşzamanlı çalıştır (geniş örneklem).
    with ThreadPoolExecutor(max_workers=len(PLATFORMS)) as executor:
        futures = {
            executor.submit(_run_scraper, name, func, query, SCRAPER_LIMIT): name
            for name, func in PLATFORMS.items()
        }
        for future in as_completed(futures):
            name, listings, error = future.result()
            results[name] = listings
            if error:
                errors[name] = error

    # Tek listeye topla + platform adını ekle.
    all_listings = []
    for name, listings in results.items():
        for listing in listings:
            listing["platform"] = name
            all_listings.append(listing)

    # Zenginleştirme: DKK, alaka skoru, özet, görsel analiz.
    with ThreadPoolExecutor(max_workers=4) as executor:
        enriched = list(executor.map(lambda x: _enrich_listing(x, query), all_listings))

    # Akıllı filtreleme (alaka + fiyat aralığı)
    filtered = filter_listings(
        enriched,
        query,
        min_price_dkk=min_price_dkk,
        max_price_dkk=max_price_dkk,
    )

    # Platform bazlı grupla.
    grouped = {name: [] for name in PLATFORMS}
    for listing in filtered:
        grouped.setdefault(listing["platform"], []).append(listing)

    # En ilgili + en ucuz sıralama ve kullanıcı limiti kadar kırpma.
    def sort_key(item):
        return (
            -int(item.get("relevance_score", 0)),
            item.get("price_dkk") is None,
            item.get("price_dkk") if item.get("price_dkk") is not None else 0,
        )

    for name in grouped:
        grouped[name].sort(key=sort_key)
        grouped[name] = grouped[name][:user_limit]

    # Karşılaştırma özeti (gösterilen sonuçlar üzerinden)
    comparison = []
    for name, listings in grouped.items():
        prices = [l["price_dkk"] for l in listings if l.get("price_dkk") is not None]
        comparison.append(
            {
                "platform": name,
                "count": len(listings),
                "cheapest": min(prices) if prices else None,
                "average": round(sum(prices) / len(prices), 2) if prices else None,
                "error": errors.get(name),
            }
        )
    comparison.sort(
        key=lambda c: (c["cheapest"] is None, c["cheapest"] if c["cheapest"] is not None else 0)
    )

    _ensure_ready()
    ollama_model = ollama_state.get("model") or "—"

    return render_template(
        "results.html",
        query=query,
        grouped=grouped,
        comparison=comparison,
        errors=errors,
        ollama_model=ollama_model,
        user_limit=user_limit,
        min_price_dkk=min_price_dkk,
        max_price_dkk=max_price_dkk,
        filters_active=(min_price_dkk is not None or max_price_dkk is not None),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port, debug=True)
