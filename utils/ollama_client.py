"""
Ollama istemcisi.

Her ilan metni için kısa, Türkçe bir özet üretir. Ollama yerel olarak
http://localhost:11434 adresinde çalışmalıdır. Model adı otomatik tespit
edilir: OLLAMA_MODEL ortam değişkeni ayarlı değilse, /api/tags ile mevcut
modeller listelenir ve içinde "llama" geçen ilk model seçilir. Ollama
erişilemezse veya hiç model yoksa hata fırlatmaz; boş string döndürür ki
uygulama akışı bozulmasın.
"""

import logging
import os

import requests

logger = logging.getLogger("price-compare.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Ayarlı değilse None; başlangıçta /api/tags ile otomatik seçilir.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL")
_REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

PROMPT_TEMPLATE = (
    "Aşağıdaki ikinci el ürün ilanını en fazla 2 kısa cümleyle Türkçe olarak "
    "özetle. Ürünün ne olduğunu ve dikkat çeken özelliklerini vurgula. "
    "Yorum ekleme, sadece özet ver.\n\nİlan:\n{text}\n\nÖzet:"
)

# Ollama durumunu ve seçilen modeli süreç boyunca bir kez belirle.
_state = {"checked": False, "ok": False, "model": None}


def _detect_model():
    """
    Ollama'ya erişip kullanılacak modeli belirler.

    Döndürür: (erişilebilir_mi: bool, model_adı: str|None)
    """
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.RequestException:
        logger.warning(
            "Ollama'ya (%s) erişilemedi. Özetler atlanacak. "
            "Ollama'yı başlatmak için: `ollama serve`.",
            OLLAMA_URL,
        )
        return False, None

    try:
        data = resp.json()
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except (ValueError, AttributeError):
        models = []

    # 1) Ortam değişkeniyle model belirtilmişse onu kullan.
    if OLLAMA_MODEL:
        logger.info("Ollama modeli: %s kullanılıyor (OLLAMA_MODEL)", OLLAMA_MODEL)
        return True, OLLAMA_MODEL

    # 2) Hiç model yoksa uyar.
    if not models:
        logger.warning(
            "Ollama'da hiç model bulunamadı. Terminalde: ollama pull llama3"
        )
        return True, None

    # 3) İçinde "llama" geçen ilk modeli otomatik seç.
    chosen = next((m for m in models if "llama" in m.lower()), None)
    # 4) llama yoksa mevcut ilk modele düş.
    if not chosen:
        chosen = models[0]
        logger.warning(
            "Ollama'da 'llama' içeren model yok; '%s' modeli kullanılacak. "
            "Öneri: ollama pull llama3",
            chosen,
        )
    logger.info("Ollama modeli: %s kullanılıyor", chosen)
    return True, chosen


def _ensure_ready():
    """Ollama erişimini ve model seçimini bir kez yapıp durumu döndürür."""
    if not _state["checked"]:
        ok, model = _detect_model()
        _state["ok"] = ok
        _state["model"] = model
        _state["checked"] = True
    # Kullanılabilir sayılması için hem erişim hem bir model gerekir.
    return _state["ok"] and bool(_state["model"])


def summarize_listing(text):
    """İlan metni için Ollama ile kısa özet üretir."""
    if not text or not _ensure_ready():
        return ""

    payload = {
        "model": _state["model"],
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
