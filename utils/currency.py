"""
Döviz çevirimi yardımcıları.

Tüm fiyatlar DKK (Danimarka Kronu) cinsine çevrilir. Öncelikle
exchangerate-api'nin ücretsiz uç noktası denenir; başarısız olursa
elle tanımlanmış sabit kurlara düşülür. Kurlar 1 saat önbelleğe alınır.
"""

import logging
import time

import requests

logger = logging.getLogger("price-compare.currency")

# Elle tanımlı yedek kurlar: 1 birim -> DKK (yaklaşık, güncellenebilir).
FALLBACK_RATES = {
    "DKK": 1.0,
    "EUR": 7.46,
    "USD": 6.90,
    "TRY": 0.17,
    "GBP": 8.70,
    "SEK": 0.63,
    "NOK": 0.62,
}

_CACHE = {"rates": None, "ts": 0.0}
_CACHE_TTL = 3600  # 1 saat


def _fetch_rates():
    """DKK bazlı kurları uzak API'den çeker (base=DKK)."""
    url = "https://open.er-api.com/v6/latest/DKK"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") == "success" and "rates" in data:
            # API 1 DKK -> X birim verir. Bize X birim -> DKK lazım.
            rates = {}
            for cur, val in data["rates"].items():
                if val:
                    rates[cur] = 1.0 / val
            rates["DKK"] = 1.0
            return rates
    except requests.RequestException as exc:
        logger.warning("Kur API'si başarısız, yedek kurlar kullanılacak: %s", exc)
    return None


def _get_rates():
    now = time.time()
    if _CACHE["rates"] and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["rates"]

    rates = _fetch_rates()
    if not rates:
        rates = dict(FALLBACK_RATES)
    else:
        # API'de olmayan birimler için yedeklerle tamamla.
        for cur, val in FALLBACK_RATES.items():
            rates.setdefault(cur, val)

    _CACHE["rates"] = rates
    _CACHE["ts"] = now
    return rates


def to_dkk(amount, currency):
    """Verilen tutarı DKK'ya çevirir ve 2 ondalığa yuvarlar."""
    if amount is None:
        return None
    currency = (currency or "DKK").upper()
    if currency == "DKK":
        return round(float(amount), 2)

    rates = _get_rates()
    rate = rates.get(currency)
    if rate is None:
        rate = FALLBACK_RATES.get(currency)
    if rate is None:
        logger.warning("Bilinmeyen para birimi '%s', çevrilemedi.", currency)
        return None
    return round(float(amount) * rate, 2)
