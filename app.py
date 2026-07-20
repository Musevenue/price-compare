"""
Fiyat Karşılaştırma Uygulaması (price-compare)
-----------------------------------------------
dba.dk, Facebook Marketplace ve Sahibinden.com platformlarından
ürün ilanlarını tarar, fiyatları DKK'ya çevirir ve Ollama (llama3)
ile her ilan için kısa bir özet üretir.

Yerel (localhost) çalışacak şekilde tasarlanmıştır.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request

from scrapers.dba import scrape_dba
from scrapers.facebook import scrape_facebook
from scrapers.sahibinden import scrape_sahibinden
from utils.currency import to_dkk
from utils.ollama_client import summarize_listing

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
    "Sahibinden.com": scrape_sahibinden,
}


def _run_scraper(name, func, query, limit):
    """Tek bir platformu tarar, hataları zarifçe ele alır."""
    try:
        listings = func(query, limit=limit) or []
        logger.info("%s: %d ilan bulundu", name, len(listings))
        return name, listings, None
    except Exception as exc:  # noqa: BLE001 - platform hatasını yut
        logger.exception("%s taranırken hata: %s", name, exc)
        return name, [], str(exc)


def _enrich_listing(listing):
    """İlanı DKK fiyatı ve Ollama özeti ile zenginleştirir."""
    price = listing.get("price")
    currency = listing.get("currency", "DKK")
    price_dkk = None
    if price is not None:
        try:
            price_dkk = to_dkk(price, currency)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fiyat dönüştürülemedi (%s %s): %s", price, currency, exc)
    listing["price_dkk"] = price_dkk

    # Ollama özeti (senkron). Ollama erişilemezse boş kalır.
    text_parts = [listing.get("title", ""), listing.get("description", "")]
    text = " ".join(p for p in text_parts if p).strip()
    listing["summary"] = summarize_listing(text) if text else ""
    return listing


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["GET", "POST"])
def search():
    query = (request.values.get("query") or "").strip()
    try:
        limit = int(request.values.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 20))

    if not query:
        return render_template("index.html", error="Lütfen bir ürün adı girin.")

    logger.info("Arama başlatıldı: '%s' (limit=%d)", query, limit)

    results = {}
    errors = {}

    # Platform taramalarını eşzamanlı (concurrent) çalıştır.
    with ThreadPoolExecutor(max_workers=len(PLATFORMS)) as executor:
        futures = {
            executor.submit(_run_scraper, name, func, query, limit): name
            for name, func in PLATFORMS.items()
        }
        for future in as_completed(futures):
            name, listings, error = future.result()
            results[name] = listings
            if error:
                errors[name] = error

    # Her ilanı DKK fiyatı ve Ollama özeti ile zenginleştir.
    all_listings = []
    for name, listings in results.items():
        for listing in listings:
            listing["platform"] = name
            all_listings.append(listing)

    with ThreadPoolExecutor(max_workers=4) as executor:
        enriched = list(executor.map(_enrich_listing, all_listings))

    # Platform bazlı grupla ve fiyata göre (ucuzdan pahalıya) sırala.
    grouped = {name: [] for name in PLATFORMS}
    for listing in enriched:
        grouped.setdefault(listing["platform"], []).append(listing)

    def sort_key(item):
        p = item.get("price_dkk")
        return (p is None, p if p is not None else 0)

    for name in grouped:
        grouped[name].sort(key=sort_key)

    # Karşılaştırma özeti: platform başına en ucuz / ortalama / adet.
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

    return render_template(
        "results.html",
        query=query,
        grouped=grouped,
        comparison=comparison,
        errors=errors,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
