# yourkiosk — TARAYICI (Chromium kiosk) GÖSTERİM MODU

Qt uygulamasıyla **aynı görünüm, aynı davranış ve aynı veri kuralları**; alternatif olarak
tarayıcının kiosk modunda çalışır. Cihaza özgü tek bilgi adresteki **cihaz kimliğidir**:

```
http://127.0.0.1:8090/index.html?clientID=<cihaz>&veri=yerel
```

## Neden bu klasör?

| Konu | Qt (`kiosk/`) | Bu arayüz (`web/`) |
|---|---|---|
| Çalıştırma | `python3 main.py` (PyQt6) | `chromium --kiosk --app=<adres>` |
| Veri | `core/veri_kaynagi.py` | `src/veri/kaynak.ts` (aynı dosyalar, aynı kurallar) |
| Görsel değerler | `config.py` + `ui/*` (satır içi) | **`kiosk/tools/web_disa_aktar.py` üretir** → `src/veri/yerlesim.json` |
| Önbellek | `onbellek/` klasörü (diskte) | Cache Storage (kalıcı Chromium profilinde) |

Ölçü, punto ve renkler **elle yazılmaz**; `config.py` + Qt kaynağından üretilir ve
`kiosk/tests/test_web_yerlesim.py` hem dosyanın güncelliğini hem de Qt kaynağındaki
değerlerin hâlâ yerinde olduğunu denetler (sessiz sapma olmaz).

## Kurulum

```bash
npm install --include=dev     # NODE_ENV=production olan ortamlarda --include=dev şart
npm run build                 # dist/ — TARAYICI MODU İÇİN ZORUNLU (bkz. CALISTIRMA.md)
npm run test                  # 86 birim testi (veri, ayarlar, döngü, kuşak, yerleşim, gerçek render)
```

> **Önemli:** Tarayıcı modu **derlenmiş** arayüzü sunar (`web/dist`). Kaynak klasör
> (`index.html` → `/src/main.ts`) tarayıcıda çalışmaz ve **beyaz ekran** olarak görünür;
> bu yüzden `npm run build` çalıştırılmalıdır. Ayrıntılı adımlar: [`CALISTIRMA.md`](CALISTIRMA.md).

## Çalıştırma

Tarayıcı modu, kiosk tarafındaki tek ayarla açılır (`kiosk/ayarlar.json` → `calistirma` grubu,
panelde **Ayarlar → Çalıştırma modu**):

```json
{ "calistirma": { "mod": "tarayici", "web_veri_modu": "yerel" } }
```

```bash
cd kiosk
python3 main.py                        # mod=tarayici ise Chromium kiosk açılır
python3 tools/tarayici_kiosk.py        # doğrudan tarayıcı modu
python3 tools/tarayici_kiosk.py --kuru  # yalnızca adres + komutu yazdır (hiçbir şey açılmaz)
```

`main.py` bu modda **Qt'yi hiç yüklemez**: yerel bir HTTP sunucusu `web/` klasörünü ve
izinli veri dosyalarını yayınlar, Chromium kiosk olarak açılır.

## Adres parametreleri

| Parametre | Zorunlu | Açıklama |
|---|---|---|
| `clientID` | ✓ | Cihaz kimliği (`makinebilgileri.json` → `clientID`). `match.json` içinde bu kimlikle ilçe/bölge bulunur |
| `veri` | – | `yerel` (varsayılan; veri cihazdaki dosyalardan) veya `https` (`DOSYA_ADRESI`'nden) |
| `taban` | – | `veri=https` iken veri kök adresi (launcher `DOSYA_ADRESI`'ni yazar) |
| `yerlesim` | – | Yalnızca test: ölçek zorlaması (ör. `0.5`) |

Kimlik yoksa/`match.json` içinde bulunamazsa ekranda **okunabilir bir hata kartı** çıkar
(beyaz ekran yerine); kart, başlatma biçimini de gösterir.

## Davranış (Qt ile birebir)

* **Döngü:** her turda bir sonraki nöbetçi (10 sn); liste bitince aktif yayın varsa yayın modu,
  yoksa başa dön. `yayinlar` kapalıysa yayına hiç geçilmez; `nobet_listesi` kapalıysa yalnız-yayın döngüsü.
* **Yayın:** `start ≤ şimdi < end` (yarı açık) penceresine göre; süre `duration` (1–60 sn);
  görsel alınamazsa o yayın atlanır.
* **Orta panel geçişi:** çıkan aşağı, giren yukarıdan — 1800 ms `InOutCubic` (Qt `QPropertyAnimation`).
* **Sol panel:** satır yüksekliği 5'li tabana göre sabit; 5'ten fazla kayıtta liste vurguyu takip
  eder, kaydırma orta geçişle **aynı anda ve aynı sürede** (8 kayıtta hedefler `0,0,0,0,0,218,436,654`).
* **Kuşak:** yalnızca yayın görünümünde, görselin üstünde; konum Qt formülüyle
  (`x = şerit − oran×(şerit+yazı)`), tekli modda giriş/durma/çıkış fazları.
* **Kayıt görünürlüğü:** `start ≤ şimdi < end`; penceresi okunamayan kayıt **gizlenmez**;
  hepsi düşerse tümü gösterilir. İlçe/bölge süzme **ağaç anahtarlarına** göre yapılır (Qt ile aynı).
* **Özellik bayrakları:** `nobet_listesi`, `yayinlar`, `kayan_yazi`, `saat_tarih` (kapsam ayarları dâhil).

## Önbellek (maliyet)

`lastupdate.json` değişmediyse büyük veri dosyası **ağdan çekilmez** (Cache Storage’dan gelir);
yayın görselleri ilk gösterimde bir kez indirilir, sonrakiler cihazdan gelir. Süresi geçen
görseller (yayının `end` + `onbellek.gorsel_saklama_gun`) ve veride artık geçmeyenler silinir.
Chromium kalıcı profili (`kiosk/.tarayici-profil/`) bu önbelleği taşır — **gizli/incognito mod kullanılmaz**.

## Güvenlik (yerel sunucu)

* Yalnızca `127.0.0.1` üzerinde dinler; `..`/sembolik bağ ile kök dışına çıkma reddedilir.
* Beyaz liste: yalnızca arayüz dosyaları + `lastSystemData.json`, `lastupdate.json`, `match.json`,
  `sablon.json`, `ayarlar.json`, `kapsam-ayarlari.json` + `bg_layout/*.png`, `logo.png`.
* `makinebilgileri.json` (cihaz kimliği) ve günlükler **hiç sunulmaz** (403) — kimlik URL'den gelir.
* JSON yanıtları `no-store`, görseller `max-age` ile verilir.

## Testler

```bash
npm run test                                    # arayüz testleri
cd ../kiosk && bash tools/test.sh               # kiosk + tarayıcı modu testleri
```

Sorun çıkınca: `python3 tools/tarayici_kiosk.py --tani` → arayüz derlenmiş mi, tarayıcı sürümü ne,
veri/kimlik eşleşmesi tamam mı, hangi dosya hangi HTTP koduyla sunuluyor — hepsini yazar ve
**tarayıcı konsolunu terminale döker**. Arayüz çizilemezse sayfa, boş ekran yerine hatayı gösteren
bağımsız bir kart çizer (`index.html` içindeki güvenlik ağı).

Tarayıcı görsel doğrulaması bu depoda yapılmaz (bu makinede kullanılabilir tarayıcı yok);
cihazda `python3 tools/tarayici_kiosk.py --kuru` ile adresi görüp Chromium'da açabilirsiniz.
