"""
Ollama (llama3) istemcisi.

Her ilan metni için kısa, Türkçe bir özet üretir. Ollama yerel olarak
http://localhost:11434 adresinde çalışmalıdır. Ollama erişilemezse
(kapalıysa, model yoksa vb.) hata fırlatmaz; boş string döndürür ki
uygulama akışı bozulmasın.
"""

import logging
import os

import requests

logger = logging.getLogger("price-compare.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
_REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

PROMPT_TEMPLATE = (
    "Aşağıdaki ikinci el ürün ilanını en fazla 2 kısa cümleyle Türkçe olarak "
    "özetle. Ürünün ne olduğunu ve dikkat çeken özelliklerini vurgula. "
    "Yorum ekleme, sadece özet ver.\n\nİlan:\n{text}\n\nÖzet:"
)

# Ollama'nın erişilebilir olup olmadığını süreç boyunca bir kez kontrol et.
_availability = {"checked": False, "ok": False}


def _is_available():
    if _availability["checked"]:
        return _availability["ok"]
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        _availability["ok"] = resp.status_code == 200
    except requests.RequestException:
        _availability["ok"] = False
    _availability["checked"] = True
    if not _availability["ok"]:
        logger.warning(
            "Ollama'ya (%s) erişilemedi. Özetler atlanacak. "
            "Ollama'yı başlatmak için: `ollama serve` ve `ollama pull llama3`.",
            OLLAMA_URL,
        )
    return _availability["ok"]


def summarize_listing(text):
    """İlan metni için Ollama llama3 ile kısa özet üretir."""
    if not text or not _is_available():
        return ""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": PROMPT_TEMPLATE.format(text=text[:1500]),
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 120},
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=_REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()
    except requests.RequestException as exc:
        logger.warning("Ollama özet üretimi başarısız: %s", exc)
        return ""
