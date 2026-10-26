# yourkiosk — eczane nöbet ekranı (referans sürüm + güvenlik adımları)

Bu klasör, `../yayinli moduler olan versiyon` projesinin **birebir kopyasıdır** ve üzerine
istenen güvenlik adımları uygulanmıştır. **Görsel tasarıma (punto, renk, oran, yerleşim)
hiç dokunulmadı** — yalnızca veri kaynağı, ağ erişimi, görsel denetimi ve hata yönetimi
değişti.

```
kiosk/
├── main.py                # giriş noktası (--pencere ile pencereli mod)
├── pharmacy_app.py        # ana pencere (referans tasarım)
├── config.py              # ayarlar + veri kaynağı + güvenlik sınırları
├── utils.py               # veri yükleme + telefon biçimlendirme (format_phone aynı)
├── logging_setup.py       # dosya + stderr günlüğü
├── fontconfig_setup.py    # eksikse asgari fontconfig (sadece bu makine için)
├── core/                  # data_handler, broadcast_manager, timer/animation
├── ui/                    # nobet_widget, yayin_widget (tasarım değişmedi)
├── components/            # right_content_block (tasarım değişmedi)
├── security/              # image_policy.py (saf Python) · safe_image.py · network.py
├── data/
│   ├── ham_hakkisabah.json   # hakkisabah.com'dan alınan ham veri (14.10.2026)
│   ├── veri_guncel.json      # tarihleri ileriye kaydırılmış veri (uygulama bunu okur)
│   └── ornekdata_7li.json    # referans örnek dosya (yedek kaynak)
├── tools/
│   ├── shift_dates.py     # tarih kaydırıcı (üretim aracı)
│   ├── setup_qt_libs.py   # (geliştirme makinesi) eksik Qt kütüphanelerini aşamalar
│   └── test.sh            # test çalıştırıcı
└── tests/                 # birim + belge testleri
```

---

## 1. Çalışma akışı (sunucu dosyaları → cihaz)

Kiosk cihazı şu sırayı izler:

| # | Dosya | Rol |
|---|---|---|
| 1 | `lastupdate.json` | Nöbet verisi en son ne zaman işlendi (zaman damgası). Cihaz **saatte bir** bakar; damga cihazdakinle aynıysa hiçbir şey yapmaz |
| 2 | `match.json` | İlçe/bölge → **makine id'leri**. Cihaz kendi `clientID`'sini burada arar ve hangi `ilceId`/`bolgeId` içinde olduğunu öğrenir |
| 3 | `lastSystemData.json` | `sablon.json`'un doldurulmuş hâli: asıl nöbet verisi |
| 4 | `makinebilgileri.json` | Bu cihazın kendi kimliği (`clientID`) |

Cihazın bölgesini bulma ve gün seçme mantığı `core/sync.py` içindedir; veri akışı
`core/data_handler.py::load_data()` içinde yürür:

```
load_data()  →  lastupdate değişti mi?  →  hayır: bırak (ekran yeniden kurulmaz)
                                             evet: lastSystemData + match oku
                                                   → clientID ile ilçe/bölge bul
                                                   → 08:30 nöbet gününü seç
                                                   → cihazın ilçesindeki kayıtları göster
```

**Nöbet günü kuralı (sistematik):** cihaz, **kaydın kendi penceresine** bakar —
`start ≤ şimdi < end` olan nöbet **bitişine kadar** ekranda kalır:

```
14/10 08:30 ─────────────── 15/10 08:30 ─────────────── 16/10 08:30
   T20261014 (14'ünün nöbetçileri)     │  T20261015 (15'inin nöbetçileri)
   gece 02:00'de de bu gösterilir      │  08:30'dan SONRA bu gösterilir
```

* 15/10 saat **02:00** → hâlâ **14'ünün** nöbetçileri (nöbet bitmedi) ✓
* 15/10 saat **08:30** → devir: **15'inin** nöbetçileri ✓
* Şu anki pencereyi kapsayan kayıt veride yoksa: önce **en son biten** nöbet gösterilir
  (yanlış güne atlanmaz), o da yoksa başlamamış en yakın nöbet gösterilir ve günlüğe
  "veri tazelenmeli" uyarısı yazılır.

**Veri çekiminin başlangıç tarihi (kritik):** `tools/fetch_nobet.py` başlangıcı, **nöbet değişim saatini
veriden türeterek** otomatik seçer (sabit bir saat kuralı yoktur): devir saati, mevcut verideki kayıtların
`start` saatlerinin en sık görülenidir. Saat devirden **önce** ise dün başlayan nöbet hâlâ sürüyordur →
başlangıç **dün**; sonra ise **bugün**. Nöbet saatleri değişirse (ör. 09:00) araç kendini uyarlar.
Veri hiç yoksa (ilk kurulum) `config.NOBET_DEGISIM_SAATI` yalnızca **varsayılan** olarak kullanılır.
Elle geçersiz kılmak için `--baslangic YYYY-AA-GG`.

**Bitmiş nöbet listeden düşer:** aynı gün içinde farklı saatlerde çalışan nöbetler olabilir
(ör. Çayırova'da bir nöbet 08:30→23:59, diğeri 08:30→15/10 08:30). Ekranda **yalnızca kendi penceresi
devam eden** kayıtlar gösterilir; 23:59'da biten nöbet o saatten sonra listede görünmez. Gün bloğunun
penceresi, içindeki kayıtların **birleşimidir** (en erken başlangıç → en geç bitiş), böylece kısa bir
nöbet günün tamamını temsil etmez. Penceresi okunamayan kayıt (bozuk `start`/`end`) gizlenmez.

**Kapsam:** `config.KAPSAM = "ilce"` → cihazın ilçesindeki **tüm bölgeler** gösterilir (referans
`ornekdata_7li.json` örneğindeki davranış: hepsi aynı ilçede, farklı bölgeler).
`"bolge"` yapılırsa yalnızca cihazın kendi bölgesi gösterilir.

**Ekranda gösterilen alanlar** (tasarım aynı kaldı):

* **Sol liste:** `eczane` + `tel`
* **Orta kısım:** `eczane` + `tel` + `adres` + `adres_tarifi` (+ nöbet tarih aralığı)

**Alt kuşak (yayın ekranındaki kayan yazı):** yayın görseli **tam ekran** kalır; kırmızı
(`#c8102e`) şerit onun **üstüne bindirilmiş** bir katmandır (yerleşime eklenmez, `raise_()` ile
görselin üzerinde durur ve pencere boyutu değiştikçe `resizeEvent` ile yeniden konumlanır) — böylece
kuşağın altında boş/alakasız bir arka plan görünmez. Şerit ekranın en altına yapışmaz (altında
`KUSAK_ALT_BOSLUK` kadar boşluk kalır, kiosk panellerindeki overscan kırpmasını önler).

Üzerindeki beyaz kalın yazı **eczaneleri teker teker** getirir: sağdan ortaya `InOutCubic`
yumuşatmayla gelir (nöbet listesi geçişiyle aynı his), bir süre ortada durur, aynı yumuşatmayla
soldan çıkar; sıradaki kayıt sağdan girer. Biçim `ECZANE ADI - telefon` (ör. `DEVA - 0262 325 13 35`).

```python
# config.py — ALT KUŞAK (değerler 1080p için; `scale` ile ölçeklenir)
KUSAK_YUKSEKLIK   = 80     # şerit yüksekliği (px)  [referans: 60]
KUSAK_ALT_BOSLUK  = 30     # ekranın altından yukarıda kalan boşluk (px)
KUSAK_YAZI_PUNTO  = 34     # yazı puntosu           [referans: 28]
KUSAK_GIRIS_MS    = 1200   # sağdan ortaya gelme süresi
KUSAK_DURMA_MS    = 3000   # ortada durma süresi
KUSAK_CIKIS_MS    = 1200   # ortadan sola çıkma süresi
KUSAK_HIZ         = 5      # yalnızca liste modunda sabit kayma (px/adım)
KUSAK_ADIM_ARALIGI_MS = 30 # adım aralığı (ms)
KUSAK_TEKLI       = True   # True: teker teker (gir–dur–çık); False: tüm liste tek metin
```

---

## 1.1 Genel kullanım: özellikleri aç/kapa (`ayarlar.json`)

Bu kiosk **yalnızca eczane nöbeti için değil**. Örneğin yalnızca görsel yayını yapan bir kurum
nöbet listesini veya kayan yazıyı kapatabilir. Tüm anahtarlar `config.py`'de **varsayılan** olarak
durur; `ayarlar.json` yalnızca değiştirmek istediklerinizi içerir (örnek dosya:
[`ayarlar.ornek.json`](ayarlar.ornek.json)). Dosya yoksa davranış bugünküyle aynıdır.

```bash
./run.sh --ayarlari-yaz     # etkin ayarları ayarlar.json olarak yaz (sonra elle/panelden düzenle)
./run.sh --pencere          # pencere modunda çalıştır
```

| Anahtar | Varsayılan | Etkisi |
|---|---|---|
| `ozellikler.nobet_listesi` | `true` | `false` → nöbet listesi + detay ekranı **hiç gösterilmez** (yalnızca yayın/görsel modu) |
| `ozellikler.yayinlar` | `true` | `false` → yayın moduna hiç geçilmez (yalnızca nöbet ekranı) |
| `ozellikler.kayan_yazi` | `true` | `false` → yayın görünümündeki kırmızı kuşak/kayan yazı gizlenir |
| `ozellikler.saat_tarih` | `true` | `false` → nöbet ekranındaki saat/tarih yazısı boşaltılır (yerleşim bozulmaz) |
| `gorunum.sol_panel_satir` | `5` | Sol panelde satır yüksekliği bu satır sayısına göre hesaplanır → **az nöbetçide çerçeveler büyümez** (5 kişilik referans boyut korunur). Fazlasında satırlar küçülür (taşma olmaz); kaydırma/slider ileride eklenecek. |

Kurallar: `nobet_listesi` ve `yayinlar` **ikisi birden kapatılamaz** (ekranda gösterilecek bir şey
kalmalı); bu durumda nöbet listesi otomatik geri açılır ve günlüğe uyarı yazılır.

**Panel yayınında cihaza özgü anahtarlar yoktur.** Panel `ayarlar.json`u **tam belge** olarak yazar
(şemadaki her anahtar; girilmemişse varsayılanı), ancak iki grup **hiç yazılmaz**:
`tetik.push_*` (broker/kullanıcı/parola/CA/sertifika/anahtar yolu) ve `calistirma.komut_*`
(`systemctl` dizeleri + `komut_imza_zorunlu`). Bunlar cihaz başına değişir; yayına yazılsaydı panel
varsayılanı cihazın yerel parolasını ezer, `komut_imza_zorunlu: false` ise imza denetimini tüm
cihazlarda kaldırırdı. İki katman korur: panel yazmaz (`panel/src/domain/ayarBelgesi.ts::CIHAZA_OZGU`),
cihaz da yayını bu anahtarlarda yok sayar (`ayarlar.py::YEREL_ONCELIKLI`).

Diğer gruplar: `kusak` (kuşak yüksekliği/boşluğu/puntosu/zamanlamaları), `veri` (kaynak: `dosya`
ya da `https`), `ag` (izinli alan adları, portlar, zaman aşımı) ve **`gelismis`** (veri hacmi
sınırları: `max_json_bayt`, `max_json_derinlik`, `max_json_dugum`, gösterilecek kayıt/yayın sayısı…).

> `gelismis` grubu standart kullanıcı için gerekli değildir; veri 20–30 MB'a çıkarsa yönetim
> panelinden (ya da elle) yükseltilir. Her değerin **alt/üst aralığı** vardır: yanlış değer
> sessizce kabul edilmez, gerekçesi yazılır ve varsayılan kullanılır. Ayrıntı: `GUVENLIK.md` §3.

---

## 1.2 Örnek (demo) veriyle hızlı deneme

Depo, cihaza özel veri **içermez** (`.gitignore`: `makinebilgileri.json`, `lastSystemData.json`,
`match.json`, `lastupdate.json`, `data/id_eslesme.json`, günlükler, `.venv/`, `.karantina/`,
`_arsiv/`, `.cache/`). Açık kaynak olarak indirildiğinde ekranı görmek için:

```bash
python3 tools/ornek_veri.py      # 2 gün × 2 ilçe uydurma veri (clientID: ORNEK-CIHAZ-0001)
./run.sh --pencere
```

`ornek_veri.py` gerçek cihaz verisi varsa **üzerine yazmaz** (`--zorla` gerekir). Gerçek veri için
`tools/fetch_nobet.py` kullanılır (bkz. §2).

---

## 1.3 Kapsam ayarları: ilçe / bölge / cihaz bazında özellik yönetimi

`ayarlar.json` **tüm cihazlar** için varsayılandır. Aynı kiosk yazılımını kullanan farklı ilçeler/bölgeler
ya da tek bir cihaz için fark istiyorsanız `kapsam-ayarlari.json` kullanılır:

```jsonc
{
  "varsayilan": { "ozellikler": { "kayan_yazi": true } },
  "ilceler":  { "1001": { "ozellikler": { "kayan_yazi": false } } },   // o ilçede kuşak kapalı
  "bolgeler": { "2002": { "kusak": { "yazi_punto": 30 } } },            // o bölgede punto 30
  "cihazlar": { "<clientID>": { "gelismis": { "max_json_bayt": 33554432 } } }
}
```

Çözümleme sırası **varsayilan → ilce → bolge → cihaz** (en özel kazanır); yalnızca verilen anahtar
geçersiz kılınır. Kapsam kapsamında yönetilebilen gruplar: `ozellikler`, `kusak`, `gorunum`, `gelismis`
(veri kaynağı ve ağ ayarları kapsam dışıdır — cihazın kendi güvenlik sınırlarıdır).
Doğrulama `ayarlar.json` ile **aynıdır**: aralık dışı değer sessizce kabul edilmez, gerekçesi günlüğe yazılır.
Dosya yoksa davranış birebir aynıdır. Örnek: `kapsam-ayarlari.ornek.json`.

---

## 1.4 Yönetim paneli (S3 üzerinden, sunucusuz)

Depo kökünde `panel/` klasörü vardır: **Vue 3 + Vuetify 3 + TypeScript** yazılmış, tüm veriyi
**S3'ten** okuyup yazan, tek yönetici hesaplı (Cognito User Pool + Identity Pool → geçici AWS anahtarı)
bir web panelidir. Ekranlar: Durum, Genel Ayarlar, **Kapsam Ayarları**, Nöbet ve Yayınlar, Cihazlar,
Şablon, Gelişmiş.

* Panel ile kiosk **aynı kuralları** uygular (nöbet penceresi, kapsam çözümlemesi, değer aralıkları);
  ortak test verisi iki tarafta da doğrulanır.
* Ayar şeması kiosk'tan üretilir:
  `python3 tools/sema_disa_aktar.py` → `../panel/src/domain/sema.generated.json`.
  Anahtar ekler/değiştirirseniz bu aracı çalıştırın (test güncel değilse uyarır).
* Kurulum adımları (Cognito, IAM, CORS, yayınlama): `../panel/README.md`.

---

## 1.5 Sol panel kaydırması (5'ten fazla nöbetçi)

Sol panelin satır yüksekliği her zaman `gorunum.sol_panel_satir` (varsayılan 5) sayısına göre hesaplanır:
**az nöbetçide çerçeveler büyümez, çok nöbetçide küçülmez**. Nöbetçi sayısı tabanı aşarsa panel
kaydırılabilir olur ve **vurgulanan nöbetçiyi takip eder**:

```
indeks 0-4  : ilk 5 nöbetçi görünür      → kaydırma YOK
indeks 5    : vurgu alttan taştı         → panel o satırı içine alacak kadar kayar
indeks 6, 7 : her adımda biraz daha aşağı (hedefler artan: 218 → 436 → 654 px)
döngü başa  : kaydırma en üste döner
```

Kaydırma, **nöbetçi değişimi (orta geçiş) animasyonuyla AYNI ANDA ve aynı süreyle** (varsayılan
1800 ms) başlar; bağımsız bir zamanlayıcı yoktur. (Önceki sürümde ayrı bir sayaç vardı ve orta
slider'dan 1-2 sn önce aşağı/yukarı hareket ediyordu — kullanıcı bildirimiyle düzeltildi.)

| Ayar (`ayarlar.json` → `gorunum`) | Varsayılan | Açıklama |
|---|---|---|
| `sol_panel_satir` | 5 | Satır yüksekliğinin hesabında kullanılan taban satır sayısı |
| `sol_panel_otomatik_kaydirma` | true | `false` → vurgu takip edilmez, yalnızca elle kaydırma |
| `sol_panel_kaydirma_sure_ms` | 1800 | Kaydırma süresi (orta geçişle aynı olması önerilir) |
| `kaydirma_cubugu_genislik` | 12 | Kaydırma çubuğu genişliği (px, `0` → gizli) |
| `kaydirma_cubugu_renk` / `kaydirma_tutamak_renk` | `#d9dee5` / `#6b7280` | Çubuk renkleri |

Ölçüm (1080p, taban 5, 8 kayıt): satır 208 px (5'li hâlle aynı) · kaydırma alanı açık,
hedefler `[0, 0, 0, 0, 0, 218, 436, 654]` (yalnızca gerektiğinde kayar) · 12 kayıtta tek yönlü
artan 8 hedef, taşma yok. Çerçeve görseli (`box.png`), puntolar ve oranlar değişmedi.

---

## 1.6 GEÇİCİ: sol panelde 5'ten fazla nöbetçi görünümü

`tools/gecici_coklu_test.py` cihazın ilçesindeki kayıt sayısını (varsayılan 8) sahte kayıtlarla
tamamlar; sol panel kaydırmalı hâle gelir (kaydırma §1.5). Gerçek veri
`_arsiv/lastSystemData.gercek.json` olarak yedeklenir.

```bash
python3 tools/gecici_coklu_test.py --adet 8      # geçici veriyi üret
python3 tools/gecici_coklu_test.py --geri-al     # gerçek veriyi geri yükle
```

---

## 1.7 Cihaz önbelleği ve süresi geçen yayınların silinmesi (maliyet + performans)

Amaç: **her gösterimde interneti kullanmamak**. Nöbet JSON'u ve yayın görselleri cihazda
saklanır; aynı içerik tekrar gösterilirken ağa hiç çıkılmaz.

```
onbellek/
├── dizin.json     # her kaydın sha256'sı, zamanı, son gösterim tarihi, lastupdate damgası
├── veri/          # lastSystemData.json, sablon.json, match.json, makinebilgileri.json
└── gorsel/        # yayın görselleri (adres → sha256 adı)
```

| Kural | Davranış |
|---|---|
| **Geçersizleşme** | Sunucudaki `lastupdate.json` değeri değiştiyse veri önbelleği geçersizdir: büyük dosyalar yeniden indirilir. Değişmediyse **yalnızca damga dosyası** okunur (günde 24 küçük istek), veri diskten gelir |
| **Görseller** | İlk gösterimde bir kez indirilir, doğrulanır ve saklanır; sonraki gösterimlerde **ağa çıkılmaz**. Ağ/sunucu düşse bile son görsel cihazdan gösterilir |
| **Süre sonu (son gösterim tarihi)** | Yayının `end` alanı + `onbellek.gorsel_saklama_gun` (varsayılan 2 gün) geçtiyse ve artık veride geçmiyorsa görsel cihazdan **kendiliğinden silinir** |
| **Kota** | Toplam boyut `onbellek.maks_bayt`'ı (varsayılan 512 MB) aşarsa en eski kullanılan görseller silinir |
| **Bütünlük** | Kayıtların sha256'sı okuma sırasında doğrulanır; bozulmuş/oynanmış kayıt kullanılmaz, atılır |
| **Güvenlik** | Önbellekten gösterilen görsel de aynı kapıdan geçer: https + izin listesi, bayt sınırı, biçim beyaz listesi (PNG/JPEG/WEBP), piksel bütçesi (`security/image_policy.py`) |

Ayarlar (`ayarlar.json` → `onbellek` grubu; panele otomatik yansır):

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `aktif` | true | Ana anahtar (kapatılırsa eski davranış: her gösterimde indirir) |
| `klasor` | `onbellek` | Proje kökü altındaki klasör (`.gitignore`'da) |
| `maks_bayt` | 512 MB | Toplam boyut üst sınırı |
| `gorsel_saklama_gun` | 2 | Son gösterimden sonra kaç gün tutulacağı |
| `veri_lastupdate_kullan` | true | Damga değişmediyse büyük dosyaları yeniden çekme |
| `gorsel_lastupdate_yeniler` | true | Veri değiştiğinde görselleri bir kez tazele |

Teşhis/bakım aracı:

```bash
python3 tools/onbellek_durumu.py            # durum: adet, boyut, damga
python3 tools/onbellek_durumu.py --liste    # kayıtlar: url, son gösterim, kaç kez gösterildi
python3 tools/onbellek_durumu.py --bakim    # süresi geçenleri sil, kotayı uygula
python3 tools/onbellek_durumu.py --temizle  # tüm önbelleği boşalt
```

**Sunucu tarafı temizlik:** `lastSystemData.json` içindeki süresi geçen kayıtlar ve kendi
S3 kovamızdaki görsel nesneleri **panelden** silinir (Veri → Yayınlar → "Süresi geçen yayınlar");
işlem sonrası `lastupdate.json` damgası tazelenir, cihazlar saatlik kontrolde yeni veriyi alır.
İki taraf aynı ölçütü kullanır: yayının `end` (son gösterim) tarihi.

---

## 1.8 Nöbet değişikliğini ANINDA yansıtma (tetikleyici)

Veri saatte bir kontrol edilir; bir nöbet değişikliğinde cihazın beklemesini önlemek için
**iki katmanlı** kurgu vardır:

* **Panel → `tetikle.json`**: yönetici kaydı düzenleyip *Kaydet*'ten sonra *Cihazlara hemen
  bildir* düğmesine basar. Dosya kapsam taşır (`ilceId` boş/`*` = tüm cihazlar, dolu = o ilçe).
* **Cihaz**: yalnızca KÜÇÜK dosyaları (`lastupdate.json`, `tetikle.json`) kısa aralıklarla okur.
  Tarayıcı modunda yerel sunucudaki `/degisiklik` ucu ile **uzun yoklama** yapılır (tipik <1 sn).
  Qt modunda damga yoklaması `DAMGA_KONTROL_MS` ile çalışır: **MQTT push bağlıysa 120 sn, kopukken
  30 sn** (`DAMGA_KONTROL_MS_PUSH` / `DAMGA_KONTROL_MS_PUSH_YOK`), ayrıca yerel dosya izleyici
  `TETIK_IZLEME_MS` (2 sn) ve 10 turda bir `tetikle.json`/`komut.json` çapraz kontrolü devrededir.
  Büyük veri dosyası damga değişmedikçe indirilmez.
* Kural tek yerde: `core/tetik.py` (Qt uygulaması, web sunucusu ve komut satırı aracı aynı kuralı
  kullanır). Aynı tetikleyici iki kez uygulanmaz; başka ilçenin tetikleyicisi bu cihazı etkilemez.
* Cihazda elle denemek için: `python3 tools/nobet_tetikle.py --ilce <ilceId>`.

Ayrıntılı akış, ayarlar ve uçtan uca doğrulama adımları: **[NODET-DEGISIKLIGI.md](NODET-DEGISIKLIGI.md)**.

## 1.9 Uzaktan komut: yeniden başlat / uygulamayı yeniden başlat / ekranı yenile

Cihazın bulunduğu yere gitmeden **imzalı** bir komut gönderilebilir. Taşıma yolu §1.8'deki
tetikleyiciyle **aynıdır** (`komut.json`); fark, komutun çalıştırılmadan önce imza + beyaz liste
denetiminden geçmesidir. Panel `durum.json`a komut işareti yazmadığı için cihaz komut dosyasını
**10 yoklama turunda bir** çapraz kontrolde indirir: en çok **20 dakika** (push bağlı, 120 sn tur)
ya da **5 dakika** (push kopuk, 30 sn tur).

| Komut | İşlem (varsayılan) |
|---|---|
| `yeniden-baslat` | `systemctl reboot` |
| `uygulamayi-yeniden-baslat` | `systemctl restart kiosk.service` |
| `ekrani-yenile` | uygulama içi tazeleme (tarayıcı modunda sayfa yeniden yüklenir) |

```bash
# cihazda bir kez: anahtar üret (0600, depoya girmez)
python3 tools/komut_gonder.py --anahtar-olustur

# yönetici makinesinde: imzala ve S3'e koy
python3 tools/komut_gonder.py --komut uygulamayi-yeniden-baslat --cihaz 98273648723468273
aws s3 cp komut-gonderilecek.json s3://<KOVA>/kiosk/komut.json

# cihazda doğrula
python3 tools/komut_gonder.py --durum
```

Kurallar: beyaz liste (yalnız 3 komut), HMAC imza **zorunlu** (fail-closed), hedef cihaz denetimi,
tek seferlik uygulama (`komut-durum.json`), sabit `argv` (`shell` yok), kuru çalıştırma ve zaman
aşımı. Panelde komut **salt-okunur** (istemciye sır konmaz); gönderme yönetici aracıyla ya da
sunucu tarafı (Lambda + `KOMUT_ANAHTARI`) üzerinden yapılır.

Ayrıntılı kurulum, komut gönderme, sorun giderme ve geri alma: **[KOMUTLAR.md](KOMUTLAR.md)**.

## 2. Veri üretme / tazeleme

Nöbet verisinin gerçek kaynağı: `https://www.kocaelieo.org.tr/nobet-belediye/<baslangic>/<bitis>/`

```bash
# Bugünden itibaren 16 gün çek ve şablonu doldur (dosyaları proje köküne yazar)
python3 tools/fetch_nobet.py --gun 16

# 30 güne kadar çekilebilir; başlangıç tarihi verilmezse bugündür
python3 tools/fetch_nobet.py --baslangic 2026-10-14 --gun 30

# Cihazın hangi bölgeye yerleştirileceği (match.json'da o bölgeye yazılır)
python3 tools/fetch_nobet.py --cihaz-bolge "İzmit-2"

# Yayınların her gün aktif olacağı saat penceresi (varsayılan 08:30-23:59)
python3 tools/fetch_nobet.py --yayin-araligi 08:30-23:59
python3 tools/fetch_nobet.py --yayin-araligi sablon   # şablondaki 15:16-15:33 saatlerini koru

# Ağa çıkmadan, hazır bir JSON'dan üret
python3 tools/fetch_nobet.py --yerel veri.json --gun 16
```

**Yayın penceresi (alt kuşak için kritik):** alt kırmızı kuşak ve üzerindeki kayan yazı
**yalnızca yayın modunda** görünür. Cihaz nöbet listesini bitirdikten sonra *o an aktif yayın varsa*
yayın görünümüne geçer; yayın penceresi boşsa (ör. şablondaki 15:16–15:33 dışında) yayın moduna hiç
girilmez ve kuşak görünmez. `--yayin-araligi` bu pencereyi günün tamamına yayar.

**Adres kuralları (kritik):** ilk tarih = aralığın **başlangıcı** (bugün çekiyorsan bugünün tarihi
olmalı; yarın çekersen yarının tarihi), ikinci tarih = aralığın **bitişi** ve veri **en fazla 30 gün**
olabilir (`EN_FAZLA_GUN = 30`; ihlal edilirse araç hata verir).

**Üretilenler**

* `lastSystemData.json` → `Nobetler: { "T<YYYYMMDD>": { <ilceId>: [ { <bolgeId>: [kayıt] } ] } }`
  (kayıtlar: `ilce, ilceId, bolge, bolgeId, eczane, adres, tel, adres_tarifi, enlem, boylam, start, end`;
  tarihler şablondaki gibi `gg/aa/yyyy ss:dd`), ayrıca `Yayinlar` (şablondaki yayınlar **30 güne
  çoğaltılır**) ve `lastUpdate`.
* `match.json` → `{ <ilceId>: [ { <bolgeId>: [makine id'leri] } ], "lastUpdate": ... }`; cihazın
  `clientID`'si seçilen bölgeye yazılır (varsayılan `İzmit-2`).
* `lastupdate.json` → `{"lastupdate": "<zaman damgası>"}`
* `data/id_eslesme.json` → üretilen id'lerin okunabilir eşlemesi (ilçe/bölge adı → id).

`ilceId` / `bolgeId` değerleri **üretilir**: isimden türeyen, kararlı 17 haneli sayılar
(`tools/fetch_nobet.py::id_uret`), böylece her tazelemede aynı ilçe/bölge aynı id'yi alır.

`data/veri_guncel.json` + `tools/shift_dates.py` (önceki tarih kaydırma yaklaşımı) kullanılmıyor;
`_arsiv/` klasörüne taşındı, silinebilir.

---

## 3. Uygulanan güvenlik adımları

| Konu | Önce (referans) | Şimdi |
|---|---|---|
| Veri erişimi | `urlopen(url)`: zaman aşımı/boyut/şema denetimi yok | `security/network.py`: **https zorunlu**, ana makine izin listesi, `timeout`, `max_bytes`, TLS doğrulaması açık |
| Yayın görselleri | `QImage.loadFromData(...)`: biçim serbest (svg/pdf/tiff dâhil) | `security/image_policy.py` + `security/safe_image.py`: beyaz liste PNG/JPEG/WEBP, SVG/XML/HTML reddi, bayt sınırı, **başlıktan okunan piksel bütçesi**; `QImageReader.setDecideFormatFromContent(False)` + `setAllocationLimit` |
| Yerel dosya kaynağı | yok | `data/veri_guncel.json`, yoksa yedek dosyaya düşer, bozuk JSON çökme üretmez |
| Hata yönetimi | 5 yerde çıplak `except:` / `print()` | tür bazlı yakalama + `logging` (döner dosya `kiosk.log` + stderr) |
| Nöbet aralığı metni | `QDateTime.fromString(..., "yyyy-MM-dd HH:mm:ss")` (canlı veri `dd/MM/yyyy HH:mm` geldiği için boş kalıyordu) | `utils.parse_tarih` ile biçimden bağımsız ayrıştırma; metin referansla aynı |

Neden bu kadar önemli: bu kurulumda `QImageReader` **svg, svgz, pdf, tiff, gif** çözebiliyor ve Qt SVG
tarafında 2026'da açıklanan açıklar (CVE-2026-6210 CVSS 8.7, CVE-2026-78253, CVE-2026-79616,
CVE-2026-79680 VNC — düzeltme 6.11.3) tam olarak "güvenilmeyen biçim çözümleme" sınıfında.
Bu yüzden görsel, Qt'ye verilmeden önce denetleniyor. (Ayrıntılı CVE tablosu için önceki analiz
raporuna bakılabilir: `../kiosk_app/ANALIZ.md`.)

### 3.1 İkinci tur sertleştirme (ağ + veri + Qt eklentileri)

| Konu | Risk | Yapılan |
|---|---|---|
| **Yönlendirme ile izin listesi atlatma** | `urllib` yönlendirmeleri körü körüne izler; izinli bir sunucu `302` ile başka adrese gönderebilir | `security/network.py::_YonlendirmeDenetimi`: **her yönlendirme yeniden doğrulanır**; varsayılan olarak yalnızca *aynı ana makine* (`config.AG_YONLENDIRME_IZINLI = False`) |
| **Ortam vekil sunucusu (MITM)** | cihazda `https_proxy` tanımlıysa trafik araya sokulabilir | opener `ProxyHandler({})` ile kurulur — **ortam vekilleri yok sayılır** |
| **SSRF / URL enjeksiyonu** | `:8443`, `user:pass@`, `\r\n`, boşluk, çok uzun adres | yalnızca `https`, **yalnızca 443** (`AG_IZINLI_PORTLAR`), kullanıcı bilgisi yok, denetim karakteri yok, `MAX_URL_UZUNLUK` |
| **TLS** | eski protokol / sıkıştırma | en az **TLS 1.2**, sertifika + ana makine doğrulaması açık, `OP_NO_COMPRESSION`, `Accept-Encoding: identity` |
| **İçerik türü** | gövde imzası doğru ama başlık `text/html`/`application/*` | hem ağ katmanında hem `image_policy`'de **içerik türü beyaz listesi** (çift denetim) |
| **Yerel JSON dosyaları** | boyut/derinlik sınırı yoktu; sembolik bağ veya kök dışı yol okunabiliyordu | `security/veri_dogrulama.py`: **boyut**, **derinlik** (`MAX_JSON_DERINLIK`), **düğüm** (`MAX_JSON_DUGUM`) sınırı; symlink reddi; proje kökü dışına çıkma reddi |
| **Ekranı yanıltan veri** | denetim karakterleri, satır sonları, **çift yönlü yazı kontrolleri** (U+202E ile metni ters çevirme) | `temiz_metin()`: C0/C1 + bidi kontrolleri atılır, satırlar sadeleşir, uzunluk ≤ `MAX_METIN_UZUNLUK` |
| **Ekranı kilitleyen veri (DoS)** | `duration: 99999999` yayında kilitler; 100 000 kayıt listeyi dondurur | `sayi_sinirla()` ile yayın süresi **1–60 sn**; kayıt ≤ `MAX_GOSTERILEN_ECZANE`, aktif yayın ≤ `MAX_AKTIF_YAYIN` |
| **Günlükte kimlik sızması** | `clientID` ham yazılıyordu | `kimlik_ozeti()`: `9827…(17h, sha256:…)` (yalnızca özet) |
| **Durum dosyası** | `write_text` yarıda kesilirse bozuk dosya kalır, izin 644 | `atomik_yaz()`: geçici dosya + `os.replace`, izin **0600** |
| **Qt eklentileri (CVE sınıfı)** | `libqsvg/libqpdf/libqtiff/libqgif…` ve `libqvnc.so` diskte duruyor | `security/qt_sertlestirme.py`: riskli eklentiler **karantinaya** taşınır (silinmez, `.karantina/qt-eklentileri/`); `QT_PLUGIN_PATH` sabitlenir |

**Doğrulama (kod okumadan, ölçümle):**

```bash
./run.sh --guvenlik-denetimi     # arayüz açılmaz; madde madde rapor + hata varsa çıkış kodu 1
```

Örnek çıktı (bu makinede):

```
[UYARI] Qt sürümü            Qt 6.11.2 / PyQt 6.11.0 (VNC CVE-2026-79680 düzeltmesi 6.11.3+)
[ OK ] Qt eklentileri         riskli eklenti yok (1 dizin tarandı)
[ OK ] Ağ politikası          izinli host: … · port: (443,) · yönlendirme: yalnızca aynı host ·
                              TLS min: TLSv1_2 · sertifika doğrulama: açık
[ OK ] Ortam vekil sunucuları ortam vekil sunucusu yok
[UYARI] Veri kaynağı          kaynak: yerel dosya (üretimde https + DOSYA_ADRESI önerilir)
[ OK ] Veri dosyaları         … izinler uygun
[ OK ] Sınırlar (DoS)          JSON ≤4 MB, derinlik ≤32, düğüm ≤200000 · metin ≤160 · kayıt ≤60 ·
                              yayın ≤20 · yayın süresi 1-60 sn
[ OK ] Günlük                 günlük yazılabiliyor
```

`Qt eklentileri` maddesi "riskli eklenti var" derse: `./run.sh` bir sonraki açılışta karantinaya alır
(veya `python3 main.py` çağrısı da aynı işi yapar). Karantinayı tek seferlik atlamak için
`--karantina-yok`. Geri almak: `kiosk/.karantina/qt-eklentileri/` içeriğini `plugins/` altına kopyala.

---

## 4. Kurulum ve çalıştırma

```bash
# Üretim (Arch, sistem Qt paketleri kurulu)
sudo pacman -S python-pyqt6 qt6-base qt6-svg
python3 main.py

# Bu depoda geliştirme/test
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
./run.sh --pencere            # pencereli
./run.sh --pencere --log-seviyesi DEBUG
```

`requirements.txt`: `PyQt6>=6.11.0` (PyPI'da 6.11.3 henüz **yok**; tekerlek Qt 6.11.2 getirir ve
VNC eklentisi uygulama açılışında karantinaya alınır — ayrıntı: `GUVENLIK.md` §4),
`pytest`, `pytest-qt`.

**Güvenlik belgesi:** [`GUVENLIK.md`](GUVENLIK.md) — tehdit modeli, denetim noktaları şeması,
sınırların büyüklük gerekçesi, Qt temizliği öncesi/sonrası ölçümler ve doğrulama komutları.

Eksik Qt sistem kütüphaneleri olan makinelerde:

```bash
python3 tools/setup_qt_libs.py     # Arch paketlerini .qt-libs altına aşamalar (root gerekmez)
```

---

## 5. Testler

```bash
./tools/test.sh            # kiosk · panel: cd ../panel && npm run test · arayüz: cd ../web && npm run test
```

| Dosya | Kapsam |
|---|---|
| `tests/test_sync.py` | lastupdate değişim kontrolü, match.json'dan cihaz konumu, ilçe/bölge filtreleme, 08:30 gün kuralı, yayınlar, veri işleyici uçtan uca, URL tarih kuralları, id üretimi |
| `tests/test_security.py` | görsel beyaz listesi, SVG/XML/HTML reddi, piksel bombası, bayt sınırı, https + izin listesi |
| `tests/test_onbellek.py` | önbellek katmanı: lastupdate ile geçersizleşme, sha256 bütünlüğü, süre sonu/kota/artık temizliği, bozuk dizin, kapalı önbellek |
| `tests/test_gorsel_onbellek.py` | görsel akışı: ilk gösterim indirir, sonrakiler **ağa çıkmaz**; ağ yoksa önbellekten gösterir; bozuk kayıt atılır; bayat işaretlenen tazelenir |
| `tests/test_veri_kaynagi_onbellek.py` | `lastupdate` değişmediğinde büyük veri dosyaları **hiç indirilmez**; değişince yeniden alınır |
| `tests/test_tarayici.py` | tarayıcı modu: adres/komut üretimi, yerel sunucu güvenlik kapıları (beyaz liste, `..` yasağı, cihaz kimliği sunulmaz), yeniden başlatma sınırı |
| `tests/test_web_yerlesim.py` | arayüzün yerleşim verisi güncel mi + Qt kaynağındaki ölçü/punto/renk ifadeleri hâlâ yerinde mi |

Uçtan uca (offscreen) doğrulama:

```
veri yüklendi: T20261014 · İZMİT / İzmit-2 · 5 nöbetçi eczane · 60 yayın (lastupdate=...)
SOL LİSTE : DEVA | 0262 325 13 35 · ASLI | 0262 323 01 42 · ETEM | … (5 satır)
ORTA      : DEVA ECZANESİ · 0262 325 13 35
            ÖMERAĞA MAH.ABDURRAHMAN YÜKSEL CAD.BELSA SOK.NO:3-4 İZMİT
            14.10.26 08:30:00 - 15.10.26 08:30:00 TARİHLER ARASI NÖBETÇİ!
ekran görüntüsü: .cache/ekran_1920x1080.png
```

---

## 6. Bilinen durumlar / sıradaki adımlar

1. **Tasarım bilinçli olarak referansla aynı** — 1080p'de referans yerleşiminin dikey toplamı
   (125 + 45 + 480 + 3 + 640 = 1293 px > 1080 px) ekranı aştığı için alt panel bir miktar
   kırpılır. Bu, referans tasarımın kendi değeridir; dokunulmadı. İstediğinizde düzeltilebilir.
2. Canlı veri **telefon/adres yayınlamıyor**; eksik alan yerine bölge adı gösteriliyor
   (`config.EKSIK_TELEFON_YERINE_BOLGE = False` ile kapatılabilir).
3. Veri adresinde `BolgeIdleri` / `Cihazlar` (cihaz → bölge eşlemesi) yayınlanmıyor; cihazın kendi
   bölgesini öğrenmesi sunucu tarafında bu bölümlerin eklenmesini bekliyor.
4. `logo.png` yok; logo alanı boş kalıyor (uyarı günlüğe yazılır).
5. Bellek ölçümü **offscreen** yapıldı (aşağıda); gerçek ekranda GPU/EGL yüzeyleri birkaç MB ekler —
   cihazda `--gercek-ekran` ile ölçün, fark varsa paylaşın.

---

## 7. Bellek kullanımı (ölçülmüş)

Ölçüm aracı: `tools/bellek_olc.py` — uygulamayı başlatır, `/proc/<pid>/smaps_rollup`'tan
düzenli örnek alır ve hangi dosyaların ne kadar tuttuğunu döker.

```bash
python3 tools/bellek_olc.py --sure 60 --aralik 1.5      # offscreen (geliştirme makinesi)
python3 tools/bellek_olc.py --sure 300 --aralik 5 --gercek-ekran   # cihazda (önerilen)
```

**Sonuç (bu makine, Arch + PyQt6 tekerleği, offscreen, 1080p, 2 nöbetçi + yayınlar):**

| Kalem | Ortalama | En yüksek | Not |
|---|---|---|---|
| RSS (toplam) | **68.0 MB** | 68.0 MB | paylaşılan Qt kütüphaneleri dahil |
| PSS (paylaşımlı bölünmüş) | **60.7 MB** | 60.7 MB | "gerçek maliyet" |
| Özel (private) | **57.1 MB** | 57.1 MB | Python nesneleri + PyQt + önbellekler |
| Paylaşılan | 10.9 MB | 10.9 MB | başka süreçlerle ortak |

60 saniyelik izlemede **RSS değişimi +0.0 MB** → kaçak (sızıntı) yok; yayın döngüsü ve nöbet
geçişleri bellek büyütmüyor.

Belleği tutan başlıca eşlenmiş dosyalar (RSS, MB):

```
6.8  libQt6Gui.so.6        5.3  libpython3.14.so.1.0    4.4  libcrypto.so.3
4.3  libQt6Core.so.6       3.9  libQt6Widgets.so.6      3.4  QtWidgets.abi3.so
2.5  QtCore.abi3.so        2.1  locale-archive          2.0  QtGui.abi3.so
```

Yani belleğin **çoğu Qt/Python çalışma zamanı**; veri ve görsel önbelleği küçük (JSON + birkaç
görsel). Önbelleğin bellek etkisi sabittir: görsel başına **tam görsel bir kez** bellekte tutulur,
gösterim bittiğinde `QPixmap` serbest bırakılır; diskteki kopya bellek tüketmez.

Karşılaştırma fikirleri (isterseniz ölçelim): `onbellek.aktif = false` ile ağ trafiği artar ama
bellek aynı kalır — bellek farkı yaratması beklenmez, çünkü kazanç **trafik/maliyet** tarafındadır.

---

## 8. Tarayıcı (Chromium kiosk) gösterim modu — alternatif

> **Temiz klonda cihaz verisi yoktur:** `lastSystemData.json`, `match.json`, `lastupdate.json`,
> `makinebilgileri.json` depoya girmez. Eksikse başlangıçta terminal uyarısı, `--tani` raporunda
> "cihaz verisi : EKSİK" ve arayüzde ne yapılacağını söyleyen bir kart çıkar
> (`python3 tools/fetch_nobet.py`).

Aynı veriyi, **aynı görünüm ve davranışla** gösteren HTML/JS arayüzü (`../web/`) tarayıcının
kiosk modunda çalıştırılabilir. Cihaza özgü tek bilgi adresteki **cihaz kimliğidir**:

```
http://127.0.0.1:8090/index.html?clientID=<cihaz>&veri=yerel
```

### Mod seçimi (config ya da panel)

`ayarlar.json` → **`calistirma`** grubu (panelde *Ayarlar → Çalıştırma modu*):

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `mod` | `qt` | `qt` (PyQt6 penceresi) veya `tarayici` (Chromium kiosk) |
| `tarayici_yolu` | `chromium` | Tarayıcı çalıştırılabilir dosyası (bulunamazsa `chromium-browser`, `google-chrome` denenir) |
| `tarayici_ek_bayraklar` | (boş) | Chromium'a eklenecek ek bayraklar (boşlukla ayrılmış) |
| `profil_klasoru` | `.tarayici-profil` | Kalıcı profil: görsel/HTTP önbelleği burada kalır (**incognito kullanılmaz**) |
| `pencere_boyutu` | `1920,1080` | `--window-size` |
| `yeniden_baslat_s` | 5 | Tarayıcı kapanırsa kaç sn sonra yeniden açılsın (0 = açma; 60 sn'de 5 çökmede vazgeçilir) |
| `web_klasoru` | `web` | Arayüz klasörü (proje kökünde) |
| `web_sunucu_adresi` / `web_sunucu_portu` | `127.0.0.1` / `8090` | Yerel sunucu (yalnızca cihazdan erişilir) |
| `web_veri_modu` | `yerel` | `yerel` (cihazdaki dosyalar) veya `https` (`DOSYA_ADRESI`) |
| `web_yenileme_ms` | 60000 | Arayüzün veriyi yeniden kontrol aralığı |

```bash
# Doğrudan tarayıcı modu (Qt açılmaz)
python3 tools/tarayici_kiosk.py --kuru     # adres + Chromium komutunu yazdır
python3 tools/tarayici_kiosk.py            # sunucu + Chromium kiosk
python3 main.py                            # mod=tarayici ise aynı yola gider
```

### Önce arayüzü derleyin (ZORUNLU)

```bash
cd web && npm install --include=dev && npm run build      # → web/dist/
```

Tarayıcı modu **derlenmiş** arayüzü (`web/dist`) sunar; kaynak klasörün `index.html` dosyası
`/src/main.ts` ister ve tarayıcı TypeScript çalıştıramaz (**beyaz ekran**). Derlenmemişse
başlatıcı tarayıcıyı hiç açmaz, açıklayıcı hata verir (çıkış kodu 4).
Adım adım rehber: [`../web/CALISTIRMA.md`](../web/CALISTIRMA.md).

### Nasıl çalışır

1. Küçük bir **yerel HTTP sunucusu** derlenmiş arayüzü (`web/dist`) ve izinli veri dosyalarını yayınlar
   (yalnızca `127.0.0.1`; `..`/sembolik bağ reddedilir; `makinebilgileri.json` **hiç sunulmaz**).
2. Chromium `--kiosk --app=<adres>` ile açılır; sayfa `clientID` ile `match.json`dan ilçe/bölgeyi
   bulur, veriyi ve ayarları kendi çeker (yerel dosyalardan ya da `DOSYA_ADRESI`'nden).
3. Görsel değerler **Qt kaynağından üretilir**: `tools/web_disa_aktar.py` → `web/src/veri/yerlesim.json`
   (ölçü, punto, renk, kutu görselleri). `tests/test_web_yerlesim.py` hem dosyanın güncelliğini hem de
   Qt kaynağındaki ifadelerin yerinde olduğunu denetler → **tasarım sapması sessizce oluşamaz**.
4. Tasarım görselleri (`bg_layout/box.png`, `activeBox.png`, `kusak.png`, `logo.png`) kopyalanmaz,
   aynı dosyalardan sunulur.

Ayrıntılar, adres parametreleri ve davranış tablosu: [`web/README.md`](../web/README.md).
Arayüz testleri: `cd web && npm run test`.
