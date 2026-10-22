# Nöbet değişikliğini ANINDA yansıtma (tetikleyici)

Veri normalde **saatte bir** kontrol edilir (`LASTUPDATE_KONTROL_MS`). Bir nöbet değişikliği
yapıldığında cihazın bir saate kadar beklemesi istenmediği için iki katmanlı bir kurgu vardır.

## 1. Akış (yönetici → cihaz → ekran)

```
PANEL (yönetici)                     S3 / cihaz dosyaları                CİHAZ
────────────────                     ─────────────────────               ─────
1) kaydı düzenler, Kaydet ─────────▶ lastSystemData.json
2) "Cihazlara hemen bildir" ────────▶ tetikle.json  (zaman + ilceId)
                                      lastupdate.json (damga)            3) ANINDA fark eder
                                                                          4) veriyi yeniler
                                                                          5) ekran güncellenir
```

* **`tetikle.json`** (kök klasör / S3 kökü):

  ```json
  { "zaman": "2026-10-17T09:12:00", "ilceId": "30607352906750376", "bolgeId": "", "aciklama": "" }
  ```

  | Alan | Anlamı |
  |---|---|
  | `zaman` | ISO damga. Aynı tetikleyici **iki kez uygulanmaz** (bu değer karşılaştırılır). |
  | `ilceId` | Boş veya `*` → **tüm cihazlar**; doluysa **yalnız o ilçenin** cihazları hemen yenilenir. |
  | `bolgeId` | İsteğe bağlı, daha dar kapsam (doluysa tek bölge). |
  | `aciklama` | Günlükte görünecek kısa not. |

* **`lastupdate.json`** damgası değişmişse tetikleyiciye gerek yoktur; cihaz bunu da yoklar.

## 2. Cihaz tarafı (iki yol birlikte çalışır)

| Yol | Gecikme | Nerede |
|---|---|---|
| **Uzun yoklama** `/degisiklik` (yalnız tarayıcı modunda, yerel sunucu) | tipik **< 1 sn** | Sunucu, `lastupdate.json`/`tetikle.json` üst verisi değişene kadar isteği açık tutar |
| **Hızlı yoklama** `DAMGA_KONTROL_MS` (varsayılan **20 sn**) | ≤ 20 sn | Hem Qt hem tarayıcı modu: yalnız KÜÇÜK dosyalar okunur |
| Saatlik tam kontrol `REFRESH_INTERVAL_MS` | ≤ 1 saat | Emniyet ağı (her iki mod) |

Yoklama **yalnızca üst veri** okur: `lastupdate.json` (~40 bayt) ve `tetikle.json`. Büyük
`lastSystemData.json` damga değişmedikçe **indirilmez** (önbellek korunur, kota harcanmaz).

Kapsam kuralı (`core/tetik.py` ↔ tarayıcıdaki `tetikUygulanmali`, aynı kural):

1. `ilceId` boş/`*` → uygulanır,
2. `ilceId` == cihazın ilçesi → uygulanır,
3. `bolgeId` == cihazın bölgesi → uygulanır,
4. aksi hâlde **hemen uygulanmaz** (20 sn'lik yoklama + saatlik kontrol yine çalışır),
5. `zaman` ≤ son uygulanan → uygulanmaz (tekrar engeli).

## 3. Ekranda nasıl görünür?

* Yenileme **gösterimi bozmaz**: o an kaçıncı nöbetçi gösteriliyorsa o kayıt korunur
  (sol paneldeki vurgu ile orta panel aynı kayıtta kalır).
* Değişen ilçenin kaydı sırası geldiğinde (ya da o an gösteriliyorsa **anında**) yeni içerikle çıkar.
* Kuşak/yayın akışı etkilenmez; nöbet listesi uzunluğu değişirse kaydırma yeniden hesaplanır.

## 4. Kullanım

**Panelden (normal yol):** *Nöbet ve Yayınlar* ekranında kaydı düzenleyip **Kaydet**, ardından
"Cihazlara hemen bildir" kartından kapsamı (ilçe veya tüm cihazlar) seçip **Bildir**.

**Cihazda elle (test/bakım):**

```bash
cd kiosk
python3 tools/nobet_tetikle.py --ilce 30607352906750376   # yalnız o ilçe
python3 tools/nobet_tetikle.py                            # tüm cihazlar
python3 tools/nobet_tetikle.py --bolge 73154087615041151  # tek bölge
python3 tools/nobet_tetikle.py --durum                    # mevcut tetikleyiciyi göster
python3 tools/nobet_tetikle.py --sil                      # tetikleyiciyi kaldır
```

## 5. Uçtan uca doğrulama (önerilen sıra)

1. **Qt modunda:** uygulamayı çalıştır, `tools/nobet_tetikle.py` ile tetikleyici yaz →
   `kiosk.log`'da `tetikleyici uygulanıyor … → hemen yenileniyor` satırı en çok 20 sn içinde görünür.
2. **Tarayıcı modunda:** `python3 tools/tarayici_kiosk.py` ile aç; terminalde (veya ekranda `d`
   tuşuyla) `anlık bildirim: … → yenileniyor` satırı **1 saniye** içinde görünür.
3. **Kapsam denemesi:** başka bir ilçenin `ilceId`'siyle tetikleyici yaz → cihaz hemen
   yenilenmemeli (günlükte tetikleyici satırı görünmez), 20 sn'lik yoklama da damga
   değişmediği için veri çekmemeli.
4. **Panel:** *Bildir* sonrası S3'te `tetikle.json` nesnesi görünür (Durum ekranı / `aws s3 ls`).

## 6. Ayarlar (`ayarlar.json → calistirma`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `degisiklik_kontrol_ms` | `20000` | Damga + tetikleyici yoklama aralığı (5 sn – 1 saat) |
| `degisiklik_bekleme_s` | `30` | Uzun yoklamada tek isteğin en fazla açık kalma süresi |
| `tetik_dosyasi` | `tetikle.json` | Tetikleyici dosyasının adı |

## 7. Gizlilik ve güvenlik

* Yerel sunucudaki `/degisiklik` ucu **yalnız 127.0.0.1**'e açıktır ve yalnızca imza + tetikleyici
  bilgisi döner (veri içeriği taşımaz).
* `tetikle.json` bir **komut değildir**: yalnız "verini yenile" der; hangi veriyi göstereceğini
  yayınlanmış veri dosyası belirler. Cihaz komut çalıştırmaz.
* **Uzaktan komut (UYGULANDI):** `komut.json` aynı taşıma yolunu kullanır ama çalıştırılmadan önce
  beyaz liste + HMAC imza (fail-closed) + hedef cihaz + tek seferlik denetimden geçer; `argv`
  ayarlardan gelir (`shell` yok). Yeniden başlatma / uygulamayı yeniden başlatma / ekranı yenileme.
  Kurulum ve kullanım: **[KOMUTLAR.md](KOMUTLAR.md)** (`core/komut.py`, `tools/komut_gonder.py`).
  Cihaz tarafı: Qt'de `pharmacy_app.tetik_kontrol → uzak_kontrol`, tarayıcı modunda süpervizörün
  `uzak-kontrol` iş parçacığı (`core/tarayici.py::uzak_kontrol_bir_tur`).

---

## Oto tetikleme ayarı (`tetik` grubu)

| Anahtar | Tip | Varsayılan | Anlamı |
|---|---|---|---|
| `tetik.aktif` | bool | `true` | Panel yayını cihazı **beklemeden** yenilesin mi |
| `tetik.modlar` | liste | `["qt", "tarayici"]` | Oto tetiklemenin geçerli olacağı modlar |

### Davranış

1. **Panel:** ekranda görüneni değiştiren her dosya yazıldıktan sonra `tetikle.json` yazılır —
   `ayarlar.json`, `kapsam-ayarlari.json`, `sablon.json`, `lastSystemData.json`, `match.json`,
   `lastupdate.json`. (Önceden yalnız "Nöbet ve Yayınlar" ekranındaki elle "Bildir" düğmesi yazıyordu.)
2. **Cihaz:** `tetik.aktif = true` **ve** cihazın modu `tetik.modlar` içindeyse hemen yenilenir —
   Qt `DAMGA_KONTROL_MS` (≈20 sn) içinde, tarayıcı `/degisiklik` uzun yoklamasıyla tipik **<1 sn**.
3. **Kapalı / mod listede değil:** anında yenileme yok; cihaz normal aralıkta güncellenir
   (Qt `data_timer`, tarayıcı `web_yenileme_ms`). `/degisiklik` nabız gibi döner (sıcak döngü yok).
4. **Uzaktan komutlar** (`komut.json`) bu ayardan **bağımsızdır** (ayrı beyaz liste + HMAC).

### Sınır

Qt ayarları **açılışta** okur: `ayarlar.json` değişikliği (ör. `tetik.aktif`) için yeniden başlatma
gerekir. **Veri/yayın** değişiklikleri tetikleyici ile anında gelir. Tarayıcı modunda sayfa
yenilenince ayarlar da tazelenir.
