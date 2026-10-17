# Sıradaki işler (plan) — kaldığımız yerden devam

Bu dosya, oturum aralarında kaybolmaması için **bekleyen işleri kök neden + kabul ölçütü** ile
listeler. Her iş bitince "Durum" sütunu güncellenir.

**Bugünkü durum (özet):** kiosk **319** test ✓ · web **106** test ✓ · panel **104** test ✓ ·
`vue-tsc` ve üç derleme temiz ✓. Kalan tek doğrulama: **5'ten fazla nöbetçi canlı testi başarısız
(ekranda 8 yerine 2 kayıt)** — kök nedenleri aşağıda kesinleşti.

---

## İş 1 — "5'ten fazla nöbetçi" canlı doğrulaması ve iki kök neden  ⚠️ (kritik)

**Belirti:** `tools/gecici_coklu_test.py --adet 8` sonrası tarayıcı modunda hâlâ **2 kayıt**
(cihazın kendi ilçesindeki 2 bölge) görünüyor; kaydırma hiç oluşmuyor.

### Kök neden 1.a — Araç **yanlış günleri** dolduruyor ve damgayı tazelemiyor (kanıtlı)

`kiosk/tools/gecici_coklu_test.py`:

* `cogalt()` içinde doldurma **`gunler[:3]`** ile yalnız **ilk üç güne** yapılıyor
  (T20261014–16), oysa uygulama **"şimdi"yi içeren bloğu** gösteriyor (test 17 Ekim'de yapıldı →
  T20261017 = 4. blok). Sahte kayıtlar gösterilen bloğa hiç girmedi → ekranda cihazın **kendi 2
  gerçek kaydı** göründü. Aracın çıktısı da yanıltıcıydı: `ilk günde 8 kayıt (hedef 8)` diyor, ama
  **gösterilen** gün 17 Ekim'di.
* Araç `lastupdate.json` damgasını **hiç tazelemiyor** → 1.b (tarayıcı önbelleği) devreye girer ve
  veri zaten yerelde değişse bile arayüz eski gövdeyi servis etmeye devam eder.
* Hedef ilçe/bölge bulma kısmı (`makinebilgileri.json` + `match.json`) **doğru çalışıyor** — sorun
  gün seçiminde.

**Düzeltme (kabul ölçütü dahil):**

| Yapılacak | Dosya | Test |
|---|---|---|
| Hedef gün kümesi **şimdiyi içeren blok (± 1 gün)** ya da tüm bloklar olsun (ilk 3 gün DEĞİL); kayıtların kendi `start/end` penceresi yoksa pencere **blok tarihinden** türetilir, bunu hesaba kat | `kiosk/tools/gecici_coklu_test.py` | Test: 8 sahte kayıt **gösterilecek bloğa** giriyor; diğer ilçeler değişmiyor |
| `lastupdate.json` damgası tazelensin (cihazlar değişikliği fark etsin) | aynı dosya | Damganın değiştiği + web'in yenilendiği testi |
| Rapor **gösterilecek bloğu** yazsın (`ekranda gösterilecek blok: T20261017 → 8 kayıt`) | aynı dosya | Çıktı doğrulaması |
| `--geri-al` birebir geri yüklesin (hash/özet karşılaştırması) | aynı dosya | Yedek/geri yükleme testi |

### Kök neden 1.b — Tarayıcı **damgaya bağlı önbellekten** eski gövdeyi servis ediyor (kanıtlı)

`web/src/veri/kaynak.ts::sistemVerisi(damga)` → `onbellek.veriOku(ad, damga)`: kayıttaki `x-damga`
ile güncel damga **eşitse** diskteki (Cache Storage) gövde döndürülür. `lastupdate` değişmediği
sürece elle/panel kaynaklı veri değişikliği **hiç görünmez**. `damgaKontrol()` da yalnız damga
değişince yeniliyor; sunucudaki `/degisiklik` imzası ise yalnız `lastupdate.json` +
`tetikle.json` üst verisine bakıyor (`core/tarayici.py::degisiklik_imzasi`).

**Düzeltme:**

| Yapılacak | Dosya | Test |
|---|---|---|
| İmzaya `lastSystemData.json` (mtime+boyut, istenirse kısa sha256) eklensin → elle değişiklik de anında bildirilir | `kiosk/core/tarayici.py` | İmza, veri dosyası yazılınca değişiyor |
| Web'e **zorla yenileme** yolu: bildirim/tetikleyici geldiğinde tarayıcı veri önbelleği atlanıp taze indirilsin (Qt'de `load_data(zorla=True)` zaten var) | `web/src/veri/kaynak.ts`, `web/src/kiosk.ts`, `web/src/veri/onbellek.ts` | "damga aynı olsa da bildirim gelince taze gövde gösterilir" testi |
| `durum.damga` zorla yüklemede güncellensin (sonraki yoklamalar tutarlı kalsın) | `web/src/kiosk.ts` | Test |

**İş 1 kabul ölçütü (canlı):** `tools/gecici_coklu_test.py --adet 8` → tarayıcı modu →
sol panelde **8 satır**, 6. kayıt gösterilirken `d` kaplamasında `kaydırma=218px` ve liste kaymış;
`--geri-al` sonrası eski görünüm. Üç test takımı yeşil.

---

## İş 2 — Tetikleyiciyi uçtan uca canlı doğrulama  (İş 1 yüzünden yapılamadı)

Kod ve testler hazır (`core/tetik.py`, `/degisiklik` ucu, panel "Cihazlara hemen bildir", 20 sn
yoklama, `tools/nobet_tetikle.py`); **cihazda canlı** denenmedi.

| Adım | Komut / işlem | Kabul ölçütü |
|---|---|---|
| Tarayıcı modu, kendi ilçe | `python3 tools/nobet_tetikle.py --ilce 30607352906750376` | `d` kaplamasında `anlık bildirim…→yenileniyor` satırı **≤ 1 sn** |
| Başka ilçe (etkisiz olmalı) | `python3 tools/nobet_tetikle.py --ilce 47394149001009938` | Yenilenme **yok** (satır görünmez), veri çekilmez |
| Qt modu | aynı araç + `main.py` | `kiosk.log`'da `tetikleyici uygulanıyor…→hemen yenileniyor` ≤ 20 sn |
| Panel | *Nöbet ve Yayınlar* → **Kaydet** → **Bildir** | S3'te `tetikle.json` nesnesi görünür; cihaz yenilenir |
| Gösterim bozulmuyor | Yenileme sırasında 3. nöbetçi gösteriliyor olsun | Aynı kayıt kalır (indeks sıfırlanmaz), orta/sol panel senkron |

---

## İş 3 — Uzaktan komut: yeniden başlat / uygulamayı yeniden başlat  (sonraki istek)

Tasarım taslağı `kiosk/NODET-DEGISIKLIGI.md §7`'de. Özet gereksinimler:

1. **Komut S3'ten gelir** (`komutlar/` ön eki) ve **imzalıdır**: panel komutu yazar, cihaz
   indirir; imza/izin listesi denetiminden geçmeyen komut **çalıştırılmaz** (yalnız `https`, izinli
   alan adı, boyut/derinlik sınırı, beklenen alanlar).
2. **Beyaz liste:** `yeniden-baslat`, `uygulamayi-yeniden-baslat`, `ekrani-yenile`. Serbest metin
   komut **asla** çalıştırılmaz (kabuk yok, `subprocess` ile dizi argüman).
3. **Tek seferlik:** komut kimliği (`id`) + son uygulanan `id` saklanır; aynı komut iki kez uygulanmaz.
4. **Kuru çalıştırma + günlük:** her komut `kiosk.log`'a yazılır; panelde son komut ve sonucu görünür.
5. **Zamanlama:** cihaz uygun anda (yayın arasında/molada) uygular; **gösterim kesilirken**
   "yeniden başlatılıyor" durumu ekranda kısa süre gösterilir.
6. **Güvenlik:** komut betiği kendini yükseltmez; kiosk kullanıcısıyla sınırlı `systemd` yeniden
   başlatma (polkit/`systemctl --user` ya da izinli bir yardımcı script).

**Kabul ölçütü:** panelden "uygulamayı yeniden başlat" → cihaz ≤ 30 sn içinde yeniden başlar;
geçersiz imzalı/izin dışı komut **hiçbir şey yapmaz** ve günlüğe "reddedildi" yazar; testler
(imza doğrulama, beyaz liste, tekrar engeli, kuru çalıştırma) yeşil.

---

## İş 4 — Ölçüm ve belge tazeleme

* Tarayıcı modu için **bellek** ölçümü (`tools/bellek_olc.py` Qt içindi; Chromium için RSS/çocuk
  süreç toplamı) ve **ağ trafiği** sayıları (ilk gösterim / ikinci gösterim) → `kiosk/README.md §7`.
* README'lere **ekran görüntüsü** ekleme (kiosk + panel).
* `panel/MAALIYET.md` güncelleme: tetikleyici + 20 sn yoklamanın ek maliyeti (ölçülecek: ~40 bayt
  / 20 sn · cihaz başına aylık ~5 MB'a kadar; gerçek sayı ölçülüp yazılacak).

---

## İş 5 — Canlıya geçiş

`GITHUB-YUKLEME.md §10` ile aynı sıra: S3 kova + yaşam döngüsü, panel `.env.local`, Cognito/Lambda
kimlik kararı, `systemd` servisleri, güncelleme akışı (`git pull` + `npm run build` + servis
yeniden başlat), yedekleme (S3 sürümleme), cihaz durumunun panelde izlenmesi.

---

## İş sırası önerisi

| # | İş | Efor | Neden bu sırada |
|---|---|---|---|
| 1 | İş 1 (araç + önbellek/imza düzeltmesi) | ~1 tur | Kullanıcının gördüğü tek hata; diğer doğrulamaların önkoşulu |
| 2 | İş 2 (tetikleyici canlı doğrulama) | ~30 dk | Kod hazır; İş 1 bitince hemen denenir |
| 3 | İş 3 (uzaktan komut) | ~1-2 tur | Kullanıcının sıradaki isteği; güvenlik tasarımı hazır |
| 4 | İş 4 (ölçüm/belge) | ~yarım tur | Canlıya geçmeden sayıların doğru olması |
| 5 | İş 5 (canlıya geçiş) | — | Git + S3 kararlarından sonra |

---

## Bu oturumda tamamlananlar (bağlam)

* **Tarayıcı (Chromium kiosk) gösterim modu**: Qt ile birebir port (Vue 3), cihaz kimliği URL'de,
  yerel 127.0.0.1 sunucusu, derlenmiş arayüz sunumu, `--tani` teşhis raporu, `d` ekran üstü teşhis.
* **Siyah ekran / beyaz ekran hataları** çözüldü: CSS ölçülerine birim eklenmesi (birimsiz `var()` →
  `height: auto` → siyah ekran), eksik/yanlış JSON anahtarları, Cache Storage anahtar kuralları
  (geçerli http(s) URL, `keys()` → Request), `--kiosk` + GPU/zamanlama bayrakları.
* **Zamanlama/takılma düzeltmeleri**: Qt'deki **tek `cycle_timer`** kurgusuna dönüş, rAF'a bağımlı
  olmayan geçişler, kuşakta geçen-süreye göre kayma, yenilemede mevcut kaydın korunması.
* **Görsel köprüsü** `/gorsel?u=…`: CORS engeli olmadan görsel indirme + Qt ile **aynı** cihaz
  önbelleği + güvenlik kapıları (izin listesi, bayt/piksel bütçesi, SVG/HTML reddi).
* **Eksik ayar dosyaları** 404 yerine varsayılan içerikle sunulur.
* **Nöbet değişikliğini anında yansıtma**: `tetikle.json` + uzun yoklama `/degisiklik` + 20 sn damga
  yoklaması + panel düğmesi + Qt `tetik_kontrol()` + `tools/nobet_tetikle.py`.
* **Test sayıları**: kiosk 319 · web 106 · panel 104.
* **Temizlik + GitHub hazırlığı**: 156 MB Qt karantinası, önbellekler, günlükler silindi; `.gitignore`
  kök düzeyinde sıkılaştırıldı (`__pycache__` kaçağı kapatıldı); kök `README.md`, `LICENSE` (GPL-3.0),
  `GITHUB-YUKLEME.md` eklendi; yerel `git init -b main` yapıldı (commit yok).
