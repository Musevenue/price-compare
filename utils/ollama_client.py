"""
Ollama istemcisi.

- summarize_listing(text): İlan metnini kısa Türkçe özetler.
- analyze_image(image_url, title): İlan görselini indirip base64 olarak
  Ollama /api/generate endpoint'ine gönderir ve kısa görsel analizi üretir.

Notlar:
- Model seçimi otomatik tespit edilir (OLLAMA_MODEL > /api/tags ilk model).
- Model multimodal değilse görsel analiz çağrısı 500 hatası verebilir; bu
  durumda görsel analiz devre dışı bırakılır ve tekrar denenmez.
- Uygulama akışını bozmamak için tüm hatalarda boş string döndürülür.
"""

import base64
import logging
import os

import requests

logger = logging.getLogger("price-compare.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Ayarlı değilse None; başlangıçta /api/tags ile otomatik seçilir.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL")
_REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))
_IMAGE_DOWNLOAD_TIMEOUT = 10
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB

PROMPT_TEMPLATE = (
    "Aşağıdaki ikinci el ürün ilanını en fazla 2 kısa cümleyle Türkçe olarak "
    "özetle. Ürünün ne olduğunu ve dikkat çeken özelliklerini vurgula. "
    "Yorum ekleme, sadece özet ver.\n\nİlan:\n{text}\n\nÖzet:"
)

IMAGE_PROMPT_TEMPLATE = (
    "Bu ürün ilanının resmini analiz et. Başlık: {title}. "
    "Resimde ne görüyorsun? Ürün başlıkla uyuşuyor mu? "
    "Ürün gerçek mi, temiz durumda mı? En fazla 1-2 kısa cümle yaz."
)

# Ollama durumunu ve seçilen modeli süreç boyunca bir kez belirle.
_state = {"checked": False, "ok": False, "model": None}
# Görsel analiz desteği 500 ile patlarsa kapatılır.
_image_state = {"disabled": False}


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

    # 3) Mevcut ilk modeli kullan (llama, qwen, mistral vs. hepsi geçerli).
    chosen = models[0]
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


def _download_image_base64(image_url):
    """Görseli indirir, boyut kontrolü yapar ve base64 string döndürür."""
    if not image_url:
        return None

    try:
        head = requests.head(image_url, timeout=_IMAGE_DOWNLOAD_TIMEOUT, allow_redirects=True)
        content_len = head.headers.get("Content-Length")
        if content_len and int(content_len) > _MAX_IMAGE_BYTES:
            logger.info("Görsel çok büyük, atlandı: %s", image_url)
            return None
    except requests.RequestException:
        # HEAD başarısızsa GET ile devam etmeyi dene.
        pass
    except ValueError:
        pass

    try:
        resp = requests.get(image_url, timeout=_IMAGE_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        data = resp.content
        if len(data) > _MAX_IMAGE_BYTES:
            logger.info("Görsel 5MB'dan büyük, atlandı: %s", image_url)
            return None
        return base64.b64encode(data).decode("utf-8")
    except requests.RequestException as exc:
        logger.warning("Görsel indirilemedi (%s): %s", image_url, exc)
        return None


def analyze_image(image_url, title):
    """
    İlan görselini Ollama'ya gönderip kısa analiz döndürür.

    Model multimodal değilse /api/generate 500 dönebilir; bu durumda
    _image_state['disabled']=True yapılır ve sonraki çağrılarda direkt boş
    dönülür.
    """
    if not image_url or _image_state["disabled"] or not _ensure_ready():
        return ""

    img_b64 = _download_image_base64(image_url)
    if not img_b64:
        return ""

    payload = {
        "model": _state["model"],
        "prompt": IMAGE_PROMPT_TEMPLATE.format(title=(title or "")[:200]),
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 140},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=_REQUEST_TIMEOUT
        )
        # Multimodal destek yoksa genellikle 500 döner.
        if resp.status_code >= 500:
            _image_state["disabled"] = True
            logger.warning(
                "Ollama görsel analizi 500 hatası verdi; model multimodal "
                "desteklemiyor olabilir. Görsel analiz devre dışı bırakıldı."
            )
            return ""
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()
    except requests.RequestException as exc:
        # Bazı HTTPError durumlarında response yok olabilir.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status and status >= 500:
            _image_state["disabled"] = True
            logger.warning(
                "Ollama görsel analizi 500 hatası verdi; görsel analiz kapatıldı."
            )
            return ""
        logger.warning("Ollama görsel analizi başarısız: %s", exc)
        return ""
