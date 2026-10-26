# yourkiosk

Eczane **nöbet ekranı** (kiosk) uygulaması: aynı görünüm ve davranışı paylaşan **iki gösterim modu**
(Qt masaüstü + Chromium kiosk web arayüzü), **S3 tabanlı yönetim paneli** ve cihaz tarafında
**önbellek/maliyet** kurgusu.

Ekranda gösterilenler: devam eden nöbet listesi (5'ten fazla kayıtta kaydırmalı), seçili nöbetçinin
ayrıntısı, yayın görselleri, alt kuşakta kayan yazı, saat/tarih. Her özellik **aç/kapa** edilebilir;
ayarlar ilçe / bölge / cihaz kapsamında ayrı ayrı verilebilir.

---

## Ne var?

| Bölüm | Ne yapar | Teknoloji |
|---|---|---|
| **[`kiosk/`](kiosk/README.md)** | Ekran uygulaması. Veri akışı, önbellek, güvenlik denetimleri, yerel web sunucusu, tarayıcı başlatıcı, teşhis araçları | Python + PyQt6 |
| **[`web/`](web/README.md)** | Qt görünümünün **birebir** web karşılığı (Chromium kiosk modu için) | Vue 3 + Vite + TypeScript |
| **[`panel/`](panel/README.md)** | Yönetim paneli: veri/ayar/yayın düzenleme, süresi geçenleri temizleme, cihazlara bildirim | Vue 3 + Vuetify 3 + AWS (S3/Cognito veya Lambda) |

## Öne çıkan özellikler

* **İki gösterim modu, tek davranış:** `mod = qt | tarayici` ayarla seçilir. Tarayıcı modunda cihaz
  kimliği yalnızca URL'de taşınır: `index.html?clientID=<cihaz>&veri=yerel|https`.
* **Cihaz önbelleği:** veri ve görseller cihazda tutulur; `lastupdate` damgası değişmedikçe büyük
  dosyalar **indirilmez**, yayın görselleri ikinci gösterimde internetten **gelmez**. Süresi geçen /
  artık kullanılmayan görseller cihazdan ve S3'ten silinir.
* **Nöbet değişikliğini anında yansıtma:** panel `tetikle.json` yazar; cihaz kendi ilçesini
  ilgilendiren tetikleyiciyi görünce **beklemeden** yenilenir (tarayıcı modunda uzun yoklama ile
  genelde 1 sn, Qt modunda en çok 120 sn — push bağlıyken anlıklık MQTT'den, yoklama push kapalıysa
  30 sn). Ayrıntı: [`kiosk/NODET-DEGISIKLIGI.md`](kiosk/NODET-DEGISIKLIGI.md).
* **Güvenlik:** yalnız beyaz listedeki alan adları, yalnız HTTPS, bayt/piksel bütçesi, SVG/HTML
  reddi, cihaz kimliği hiç sunulmaz, yerel sunucu yalnız `127.0.0.1`. Ayrıntı: [`kiosk/GUVENLIK.md`](kiosk/GUVENLIK.md).
* **Maliyet bilinci:** S3/veri trafiği ve Lambda alternatifi tablolarla: [`panel/MAALIYET.md`](panel/MAALIYET.md).

## Hızlı başlangıç

```bash
# 1) Ekran uygulaması (Qt)
cd kiosk
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 tools/fetch_nobet.py          # cihaz verisini çek (lastupdate + match + lastSystemData)
python3 main.py                       # ayarlar.json yoksa varsayılanlarla çalışır

# 2) Tarayıcı (Chromium kiosk) modu
cd ../web && npm install --include=dev && npm run build   # DERLEME ZORUNLU (kaynak .ts tarayıcıda çalışmaz)
cd ../kiosk && python3 tools/tarayici_kiosk.py            # yerel sunucu + kiosk başlatıcı (--tani: teşhis)

# 3) Yönetim paneli
cd ../panel && cp .env.ornek .env.local                   # AWS değerlerini gir
npm install --include=dev && npm run dev
```

Kurulumun ayrıntısı ve sorun giderme: [`kiosk/README.md`](kiosk/README.md),
[`web/CALISTIRMA.md`](web/CALISTIRMA.md), [`panel/README.md`](panel/README.md).

## Testler

```bash
cd kiosk && bash tools/test.sh          # 319 test (Qt + veri + güvenlik + tarayıcı + tetikleyici)
cd web   && npm run test                # 106 test (durum makinesi, zamanlama, önbellek, render)
cd panel && npm run test                # 104 test (veri, temizlik, şema, S3/Lambda)
```

Bu üçlü, "ekranda görünen davranış" iddialarının çoğunu (kaydırma hedefleri, geçiş süreleri, nöbet
penceresi, kuşak hızı, önbellek geçersizleşmesi, tetikleyici kapsamı) kilitler.

## Depo yapısı

```
yourkiosk/
├─ kiosk/            # ekran uygulaması (Qt + veri + güvenlik + tarayıcı modu + araçlar)
│  ├─ core/          # veri akışı, önbellek, tetikleyici, yerel web sunucusu, zamanlayıcılar
│  ├─ ui/            # nöbet paneli, yayın görseli, kuşak
│  ├─ tools/         # veri çekme, önbellek durumu, bellek ölçümü, tarayıcı başlatıcı, tetikleyici
│  └─ tests/         # 319 test
├─ web/              # Qt görünümünün birebir web portu (Chromium kiosk)
│  ├─ src/veri/      # veri kaynağı, önbellek (Cache Storage), yayın/kuşak kuralları
│  └─ tests/         # 106 test (jsdom + sahte zamanlayıcı)
└─ panel/            # yönetim paneli (S3/Cognito ya da Lambda modu)
   └─ lambda/        # Lambda modu (Cognito'suz alternatif)
```

## Belgeler

| Belge | İçerik |
|---|---|
| [`kiosk/README.md`](kiosk/README.md) | Veri akışı, ayarlar, kapsam, önbellek, bellek ölçümü, tarayıcı modu |
| [`kiosk/GUVENLIK.md`](kiosk/GUVENLIK.md) | Tehdit modeli ve uygulanan sertleştirmeler |
| [`kiosk/NODET-DEGISIKLIGI.md`](kiosk/NODET-DEGISIKLIGI.md) | Nöbet değişikliğini anında yansıtma (tetikleyici) |
| [`panel/MAALIYET.md`](panel/MAALIYET.md) | Veri/görsel maliyet kıyasları, Lambda+Lightsail senaryoları |
| [`web/CALISTIRMA.md`](web/CALISTIRMA.md) | Tarayıcı modunda adım adım çalıştırma + sorun giderme |
| [`GITHUB-YUKLEME.md`](GITHUB-YUKLEME.md) | Bu depoyu GitHub'a güvenli yükleme rehberi |
| [`GITHUB-TOKEN.md`](GITHUB-TOKEN.md) | GitHub token'ı oluşturma/verme + branch protection adımları |
| [`otomasyon/README.md`](otomasyon/README.md) | Otomasyon komutları ve akış (kısa başvuru) |
| [`otomasyon/IS-AKISI.md`](otomasyon/IS-AKISI.md) | Çok makineli iş akışı: ben + i5 (güvenlik) + i3 (karar) |
| [`otomasyon/KURULUM.md`](otomasyon/KURULUM.md) | i5/i3 makinelerine kurulum (token, klon, cron) |
| [`SIRADAKI-ISLER.md`](SIRADAKI-ISLER.md) | Bekleyen işler ve kabul ölçütleri |

## Katkı ve sorun bildirimi

* Hata/istek: GitHub Issues. Güvenlik konuları için lütfen herkese açık issue açmayın.
* Kod katkısı: her değişiklikten sonra yukarıdaki üç test takımını çalıştırın; davranış iddiaları
  testle kilitlenmelidir ("ekranda şöyle görünür" → test).

## Lisans

**GNU GPL v3.0** (bkz. [`LICENSE`](LICENSE)).

Gerekçe: proje **PyQt6** kullanıyor. PyQt6 iki lisansla sunulur: GPL v3 (ücretsiz) veya ticari
lisans. GPL v3 seçildiği için bu depo da GPL v3 olmak zorundadır. Ticari/kapalı bir dağıtım
gerekiyorsa iki yol var: (1) Riverbank'tan PyQt6 ticari lisansı almak, ya da (2) Qt tarafını
**PySide6**'ya (LGPL v3) taşımak — bu durumda depo lisansı daha esnek seçilebilir. Tarayıcı
(`web/`) ve panel (`panel/`) katmanları Qt'ye bağlı olmadığı için ayrı lisanslanabilir; bu depoda
bütünlük adına tek lisans kullanılmıştır.
