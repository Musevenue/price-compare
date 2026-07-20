# 🏷️ Fiyat Karşılaştırma (price-compare)

Yerel (localhost) çalışan bir fiyat karşılaştırma web uygulaması. Bir ürün adı
girersiniz; uygulama **dba.dk**, **Facebook Marketplace** ve **Sahibinden.com**
platformlarını aynı anda tarar, tüm fiyatları **DKK (Danimarka Kronu)** cinsine
çevirir ve her ilan için **Ollama (llama3)** ile kısa bir yapay zeka özeti üretir.
Sonuçlar modern, Bootstrap tabanlı bir arayüzde platform bazlı gruplanmış ve
ucuzdan pahalıya sıralı olarak gösterilir.

## ✨ Özellikler

- 🔎 Tek aramayla 3 platformda eşzamanlı (paralel) tarama
- 💱 Tüm fiyatlar otomatik olarak DKK'ya çevrilir (canlı kur + yedek sabit kur)
- 🤖 Her ilan için Ollama llama3 ile Türkçe içerik özeti
- 📊 Platform karşılaştırma tablosu (en ucuz / ortalama / ilan sayısı)
- 🎨 Modern, duyarlı (responsive) Bootstrap 5 arayüzü
- 🛡️ Bir platform erişilemezse uygulama çökmez, o platform "erişilemedi" olarak gösterilir

## 📁 Proje Yapısı

```
price-compare/
├── app.py                  # Flask uygulaması (ana giriş noktası)
├── scrapers/
│   ├── dba.py              # dba.dk tarayıcısı (requests + BeautifulSoup)
│   ├── facebook.py         # Facebook Marketplace tarayıcısı (Playwright + çerez)
│   └── sahibinden.py       # Sahibinden.com tarayıcısı (Playwright)
├── utils/
│   ├── ollama_client.py    # Ollama llama3 özet üretici
│   └── currency.py         # DKK döviz çevirimi
├── templates/
│   ├── index.html          # Ana arama sayfası
│   └── results.html        # Sonuç sayfası
├── static/
│   └── style.css           # Özel stiller
├── fb_login.py             # Facebook oturum kurulum scripti (bir kez çalıştırılır)
├── requirements.txt
└── README.md
```

## 🚀 Kurulum

### 1. Depoyu klonlayın

```bash
git clone https://github.com/Musevenue/price-compare.git
cd price-compare
```

### 2. Sanal ortam oluşturun ve bağımlılıkları yükleyin

```bash
python -m venv venv
source venv/bin/activate      # Windows'ta: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Playwright tarayıcılarını yükleyin

Facebook Marketplace ve Sahibinden.com taramaları Playwright kullanır:

```bash
playwright install chromium
```

## 🤖 Ollama Kurulumu (llama3)

İlan özetleri için yerel Ollama gereklidir.

1. Ollama'yı indirip kurun: <https://ollama.com/download>
2. llama3 modelini indirin:

   ```bash
   ollama pull llama3
   ```

3. Ollama servisinin çalıştığından emin olun (varsayılan adres `http://localhost:11434`):

   ```bash
   ollama serve
   ```

> **Not:** Ollama çalışmıyorsa uygulama yine de çalışır; sadece ilan özetleri
> boş kalır. Model veya adres değiştirmek için `OLLAMA_MODEL` ve `OLLAMA_URL`
> ortam değişkenlerini kullanabilirsiniz.

## 🔑 Facebook Oturum Kurulumu

Facebook Marketplace giriş gerektirir. Kendi Facebook hesabınızla oturumu
**bir kez** kurmanız yeterlidir:

```bash
python fb_login.py
```

- Açılan tarayıcı penceresinde Facebook hesabınıza giriş yapın.
- Giriş tamamlanınca terminale dönüp **ENTER**'a basın.
- Oturum çerezleri `fb_cookies.json` dosyasına kaydedilir ve sonraki tüm
  taramalarda otomatik kullanılır.

> **Güvenlik:** `fb_cookies.json` dosyası oturum bilgilerinizi içerir ve
> `.gitignore` ile depodan hariç tutulmuştur. Bu dosyayı kimseyle paylaşmayın.
>
> Farklı bir çerez dosyası yolu için `FB_COOKIES_FILE` ortam değişkenini
> ayarlayabilirsiniz. Marketplace bölgesini değiştirmek için
> `FB_MARKETPLACE_LOCATION` (varsayılan: `copenhagen`) kullanılabilir.

## ▶️ Uygulamayı Çalıştırma

```bash
python app.py
```

Ardından tarayıcınızda şu adresi açın:

```
http://127.0.0.1:5000
```

Ürün adını girin, "Ara" düğmesine tıklayın ve sonuçların platform bazlı
karşılaştırmasını görün.

## ⚙️ Ortam Değişkenleri (opsiyonel)

| Değişken                  | Varsayılan                 | Açıklama                              |
|---------------------------|----------------------------|---------------------------------------|
| `OLLAMA_URL`              | `http://localhost:11434`   | Ollama servis adresi                  |
| `OLLAMA_MODEL`            | `llama3`                   | Kullanılacak Ollama modeli            |
| `OLLAMA_TIMEOUT`          | `60`                       | Ollama istek zaman aşımı (saniye)     |
| `FB_COOKIES_FILE`         | `fb_cookies.json`          | Facebook çerez dosyası yolu           |
| `FB_MARKETPLACE_LOCATION` | `copenhagen`               | Marketplace bölgesi                   |

## 📝 Notlar ve Sınırlamalar

- Web scraping, hedef sitelerin HTML yapısına bağlıdır. Siteler yapılarını
  değiştirdiğinde ilgili tarayıcının seçicileri (selector) güncellenmelidir.
- Sahibinden.com ve Facebook güçlü bot korumalarına sahiptir; bazı aramalarda
  sonuç dönmeyebilir. Bu durumlar arayüzde zarifçe gösterilir.
- Döviz kurları `open.er-api.com` üzerinden alınır; erişilemezse koddaki
  yedek sabit kurlar kullanılır.
- Bu araç yalnızca kişisel/yerel kullanım içindir.
