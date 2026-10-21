# Sıradaki işler (plan) — kaldığımız yerden devam

Bu dosya, oturum aralarında kaybolmaması için **bekleyen işleri kök neden + kabul ölçütü** ile
listeler. Her iş bitince "Durum" sütunu güncellenir.

**Bugünkü durum (özet):** kiosk **361** test ✓ · web **108** test ✓ · panel **104** test ✓ ·
`vue-tsc` ve üç derleme temiz ✓. **İş 1 bitti** (kökteki iki neden + 10 yeni test, gerçek veriyle
uçtan uca doğrulandı, `--geri-al` parmak izi birebir). **İş 3 bitti** (uzaktan komut: imza, beyaz
liste, tek seferlik, hem Qt hem tarayıcı modu, 23 yeni test). Kalan: cihazda **canlı** doğrulamalar
(İş 1 kabul ölçütü + İş 2 adımları) ve panel `komut.json` gösterimi (tasarım onayı bekliyor).

---

#### D modu (çift onay) aktif · 21 Ekim

* Branch protection: **iki zorunlu kontrol** — `guvenlik/inceleme` (i5) + `guvenlik/karar` (i3).
* Birleştirmeyi **i3** yapar (`yaz.py --birlestir --cift-onay`), insan tıklaması yok.
* Uçtan uca doğrulandı: i3 önce → `blocked`; i5 onayı → i3 → **birleşti** (PR #12).
* `koruma-kur` freni artık yazım hatasını yakalar; kanıt yokluğu yalnız uyarı (squash-merge gerçeği).
* i5/i3 makinelerinde: `ortam-kontrol --rol i3 --yazma-dene` → `Contents: RW` şart.

## 21 Ekim (3) — cihaz verisi kazası ve koruma

* **Ne oldu:** `fetch_nobet.py` bir kez `--cihaz-bolge` verilmeden (varsayılan `İzmit-2`)
  çalıştırıldı → cihazın verisi İzmit-2 ile yeniden üretildi, `match.json` cihazı yanlış bölgeye
  bağladı (log: `T20261021 · İZMİT / İzmit-2 · 5 nöbetçi`).
* **Onarım:** veri cihazın gerçek bölgesiyle (`Çayırova 2.Bölge`, `73154087615041151`) yeniden
  üretildi; doğrulandı: `T20261021 · ÇAYIROVA / Çayırova 2.Bölge · 1 kayıt`.
* **Koruma (yeni):** araç, cihazın görünen bölgesini değiştirecek çalıştırmada **durur**
  (`DURDURULDU … --zorla`, çıkış 6); `--cikti-dizin` ile verilen yeni klasörler otomatik oluşturulur.
  3 yeni test (`bolge_degisikligi`).
* **Ders:** cihaz verisi üreten araçlarda "varsayılan değer" sessizce kimlik/konum değiştirmemeli.

## 21 Ekim (2) — kurulum sağlamlaştırma  ✅ (PR #5 açık)

* **`fetch_nobet.py`**: temiz klonda ham traceback atıyordu → artık `--kontrol`, `--cihaz-id`
  (kimlik dosyasını oluşturur), beklenen hatalar için çözüm + çıkış kodu, Python sürüm kontrolü.
  **Temiz klon + venv yok** ortamda uçtan uca doğrulandı (16 gün / 404 kayıt / 4 dosya).
* **`otomasyon/kur.sh`** (yeni): tek komut → ortam denetimi + `~/.hermes/scripts` sarmalayıcıları +
  cron komutu (`--cron` ile görev oluşturma). i5 ve i3 için ayrı ayrı denendi.
* **`otomasyon/betik/ortam-kontrol.py`** (yeni): `--rol i5|i3|kiosk|dev`; her ✗ için çözüm.
* **`topla.py`**: Python 3.8 uyumu; sarmalayıcılar `--depo` mutlak yolu geçiriyor.
* **i5 akışı uçtan uca**: PR #5'te `guvenlik/inceleme=success` + yorum + `guvenlik/onay` etiketi
  (API'den doğrulandı). **Dependabot: 0 açık uyarı.**
* **Blokaj**: PR #5'in API'den birleştirilmesi `Contents: Read and write` istiyor →
  arayüzden "Squash and merge" ya da token'a bu izin.

## 21 Ekim — temiz klon, cron, GitHub koruması  ✅ (1 blokaj)

* **Beyaz ekran / "veri bulunamadı"**: kök neden = temiz klonda cihaz verisi yok (`.gitignore`).
  Arayüz ne yapılacağını yazıyor, `--tani` "cihaz verisi: EKSİK" diyor, başlangıçta terminal uyarısı
  var; test eklendi (`test_tani_raporu_cihaz_verisi_eksikse_cozum_yazar` + web 404 kart testi).
* **GitHub**: depo **public** yapıldı (private'da branch protection/secret scanning ücretli).
  Branch protection uygulandı ve **doğrulandı** (doğrudan push `GH006 … pull request` ile reddedildi).
  Secret scanning + push protection + Dependabot açık. 4 etiket hazır.
  `yaz.py` gerçek yazma: HTTP 201 + API'den `guvenlik/inceleme=success` doğrulandı.
* **Blokaj**: token'da `Pull requests: write` ve `Dependabot alerts: read` yok → PR açılamıyor,
  dolayısıyla `main` şu an son düzeltmelerin **gerisinde** (dal: `duzeltme/temiz-klon-veri-cron`).
  Token'a iki izin eklenince PR açılıp squash merge yapılacak.
* **Dependabot 8 uyarı** (4 kritik, 4 orta) raporlandı; yerel `npm audit` iki projede de temiz →
  uyarılar büyük olasılıkla PyQt6/Qt zinciri (CVE-2026-79680 `requirements.txt` yorumunda) ve
  kilit dosyalarındaki eski sürümler. Triyaj için `Dependabot alerts: read` gerekiyor.
* **KURULUM.md** gerçek Hermes cron arayüzüyle yeniden yazıldı; `topla.py --imza/--imza-sorun`
  (monitor) eklendi; `yaz.py --ornek` şablonu; `topla.py` yanlış yolda artık sessiz sıfır vermiyor.
* **Kuşak testleri** cihazın tarihe bağlı yayın verisine bağımlıydı → sentetik kayıtlarla düzeltildi.

---

## İş 1 — "5'ten fazla nöbetçi" canlı doğrulaması ve iki kök neden  ✅ YAPILDI (canlı test kaldı)

**Durum:** iki kök neden kapatıldı, gerçek veriyle uçtan uca doğrulandı (`--adet 8` → **ekranda
gösterilecek kayıt: 8**, damga tazelendi; `--geri-al` sonrası içerik parmak izi birebir).
Testler: `kiosk/tests/test_gecici_coklu.py` (9) + imza testi. **Cihazda canlı deneme** kaldı.

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

## İş 2 — Tetikleyiciyi uçtan uca canlı doğrulama  (kod tamam, cihazda denenmedi)

**Yeni (bu turda kapatılan boşluk):** panel S3'e `tetikle.json` yazıyordu ama **cihazın onu nasıl
alacağı** tanımlı değildi (elle kopyalama varsayılıyordu). Artık cihaz, `DOSYA_ADRESI` tanımlıysa
`core/uzak.py` ile `tetikle.json` + `komut.json` dosyalarını kendisi indirir (yalnız izinli alan
adı/HTTPS/boyut sınırı; içerik aynıysa dosyaya dokunulmaz → gereksiz bildirim olmaz). Yerel kopya
değiştiği an yerel sunucunun imzası da değişir → tarayıcı uzun yoklama ile **anında** haber alır.

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

## İş 3 — Uzaktan komut: yeniden başlat / uygulamayı yeniden başlat / ekranı yenile  ✅ YAPILDI

**Uygulanan tasarım** (`kiosk/core/komut.py`, `kiosk/tools/komut_gonder.py`, `kiosk/KOMUTLAR.md`):

1. **Taşıma:** `komut.json` — tetikleyiciyle aynı yol (S3 → cihazın yerel kopyası → 20 sn'de bir
   `core/uzak.py` ile tazelenir). Yeni: `core/tetik.py::getir` ve `core/komut.py::getir` (bu,
   İş 2'nin "panel S3'e yazıyor ama cihaz nasıl alıyor" boşluğunu da kapatır).
2. **Beyaz liste:** `yeniden-baslat`, `uygulamayi-yeniden-baslat`, `ekrani-yenile`; `argv` ayarlardan
   (`KOMUT_*`), `shell` yok, dosyadan metin çalıştırılmaz.
3. **İmza zorunlu:** HMAC-SHA256 (`id|komut|cihazId|zaman`), anahtar `komut.anahtar` (0600, depo dışı);
   yok/yanlış imza → **uygulanmaz** (fail-closed). Panel istemcisine sır konmaz.
4. **Hedef cihaz** (`cihazId` boş/`*` → tümü) + **tek seferlik** (`komut-durum.json`, son 20 kayıt).
5. **Kuru çalıştırma** (`komut_kuru_calistirma` / `--kuru`), **zaman aşımı** (`komut_zaman_asimi_s`).
6. **Cihaz tarafı:** Qt → `pharmacy_app.tetik_kontrol → uzak_kontrol`; tarayıcı modu → süpervizörün
   `uzak-kontrol` iş parçacığı (`core/tarayici.py::uzak_kontrol_bir_tur`; `ekrani-yenile` tarayıcıyı
   yeniden başlatır → sayfa tazelenir).

**Açık kalanlar (bilinçli):**

* Komut uygulanırken ekranda kısa süre "yeniden başlatılıyor" bilgisi **yok** — bu bir *tasarım*
  katmanı değişikliği olduğu için kullanıcı onayı olmadan yapılmadı.
* Panelde komut **gönderme** yok (istenciye sır konmaz): yönetici aracı ya da sunucu tarafı
  (Lambda + `KOMUT_ANAHTARI`) üzerinden yapılır. Panelde son komutun **gösterilmesi** de tasarım
  onayı bekliyor (dosya `s3.listele` ile görünür, ayrı kart eklenmedi).

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
* **Test sayıları**: kiosk 352 · web 108 · panel 104.
* **İş 1 düzeltmesi**: geçici çoklu-nöbetçi aracı gösterilen bloğu dolduruyor + `lastupdate` damgasını
  tazeliyor; sunucu değişiklik imzasına `lastSystemData.json` eklendi; web'e zorla yenileme yolu.
* **İş 3 — uzaktan komut**: `core/komut.py` (beyaz liste, HMAC imza, hedef cihaz, tek seferlik, kuru
  çalıştırma, sabit `argv`), `core/uzak.py` (küçük dosya senkronu), `tools/komut_gonder.py` (imzalama
  aracı), Qt + tarayıcı modu entegrasyonu, `KOMUTLAR.md`; 23 yeni test.
* **Ayar şeması**: 8 grup / **61** anahtar (6 yeni komut ayarı); `panel/src/domain/sema.generated.json`
  yeniden üretildi.
* **GitHub**: `origin` = `git@github.com:hakkisabah/yourkiosk.git`, `main` dalı; commit'ler
  `a785fdd` (ilk, 173 dosya) ve `15bda0e` (İş 1).
* **Temizlik + GitHub hazırlığı**: 156 MB Qt karantinası, önbellekler, günlükler silindi; `.gitignore`
  kök düzeyinde sıkılaştırıldı (`__pycache__` kaçağı kapatıldı); kök `README.md`, `LICENSE` (GPL-3.0),
  `GITHUB-YUKLEME.md` eklendi; yerel `git init -b main` yapıldı (commit yok).
