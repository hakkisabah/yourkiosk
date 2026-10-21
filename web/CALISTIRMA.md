# Tarayıcı (Chromium kiosk) modu — ÇALIŞTIRMA REHBERİ

Bu rehber, yourkiosk'u **Qt yerine tarayıcıda** çalıştırmak içindir. Arayüz Qt sürümüyle
aynı görünüm/davranış ve aynı veri kurallarına sahiptir; cihaza özgü tek bilgi adresteki
**cihaz kimliğidir**.

---

## 0) Ön koşullar

| Gereken | Kontrol | Not |
|---|---|---|
| Node.js + npm | `node -v && npm -v` | Yalnızca **derleme** için gerekir (bir kez) |
| Chromium | `chromium --version` | Yoksa: `chromium-browser`, `google-chrome` de olur |
| Python + kiosk bağımlılıkları | `cd kiosk && python3 main.py --guvenlik-denetimi` | Tarayıcı modu Qt'yi hiç yüklemez ama kiosk klasörü gerekir |

> **En sık hata:** arayüz **derlenmeden** çalıştırmak. Kaynak `index.html` TypeScript ister
> (`/src/main.ts`); tarayıcı bunu çalıştıramaz → **beyaz ekran**. Çözüm 1. adımdır.

---

## 1) Arayüzü derle (ZORUNLU, bir kez)

```bash
cd web
npm install --include=dev     # NODE_ENV=production olan sistemlerde --include=dev şart
npm run build                 # → web/dist/  (index.html + assets/*.js + assets/*.css)
```

Kontrol:

```bash
ls -l web/dist/index.html web/dist/assets/
```

`web/dist/index.html` yoksa tarayıcı modu **açılmaz**; başlatıcı bunu söyleyip çıkar
(beyaz ekran bırakmaz).

> Kaynakları değiştirdiyseniz (`web/src/...`) yeniden `npm run build` çalıştırın.
> Geliştirme sırasında `npm run dev` (Vite) ile tarayıcıdan `http://127.0.0.1:5174/`
> adresini açıp canlı izleyebilirsiniz — bu **yalnızca geliştirme** içindir, üretimde
> yerel sunucu (`tools/tarayici_kiosk.py`) kullanılır.

---

## 2) Cihaz kimliğini doğrula

```bash
cd kiosk && cat makinebilgileri.json    # {"clientID": "98273648723468273"}
```

Bu kimlik `match.json` içinde bulunmalı (ilçe/bölge eşlemesi). Bulunamazsa arayüz
**beyaz ekran değil**, okunabilir bir hata kartı gösterir (kart, başlatma biçimini de yazar).

---

## 3) Modu seç: `qt` (varsayılan) veya `tarayici`

**a) Ayar dosyasıyla** — `kiosk/ayarlar.json` (yoksa oluşturun; **düz grup yapısı**):

```json
{
  "calistirma": {
    "mod": "tarayici",
    "web_veri_modu": "yerel"
  }
}
```

**b) Panelle** — Panel → *Ayarlar* → **Çalıştırma modu (Qt / tarayıcı)** bölümü → `mod = tarayici`
→ Kaydet. (Şema kiosk'tan üretilir; panelde tüm `calistirma` anahtarları açıklamalarıyla görünür.)

Sık kullanılan anahtarlar:

| Anahtar | Örnek | Açıklama |
|---|---|---|
| `mod` | `tarayici` | `qt` \| `tarayici` |
| `tarayici_yolu` | `chromium` | Bulunamazsa `chromium-browser`/`google-chrome` denenir |
| `tarayici_ek_bayraklar` | `--start-fullscreen --disable-gpu` | Boşlukla ayrılmış ek bayraklar |
| `web_veri_modu` | `yerel` \| `https` | `yerel`: cihazdaki JSON'lar · `https`: `DOSYA_ADRESI` |
| `web_sunucu_portu` | `8090` | Yerel sunucu portu (yalnızca 127.0.0.1) |
| `yeniden_baslat_s` | `5` | Tarayıcı kapanırsa kaç sn sonra açılsın (0 = açma) |

---

## 4) Çalıştır

```bash
cd kiosk
python3 main.py                       # mod=tarayici ise Chromium kiosk açılır (Qt yüklenmez)
```

Alternatif (modu geçici olarak atlayarak):

```bash
python3 tools/tarayici_kiosk.py --kuru            # yalnızca adres + komutu yazdır
python3 tools/tarayici_kiosk.py                   # sunucu + Chromium kiosk
python3 tools/tarayici_kiosk.py --tani            # ÖN KONTROL + tarayıcı konsolunu terminale dök (sorun çıkınca)
python3 tools/tarayici_kiosk.py --port 8091 --veri-modu https --log-seviyesi DEBUG
```

`--kuru` çıktısı şöyle görünür:

```
adres : http://127.0.0.1:8090/index.html?clientID=98273648723468273&veri=yerel
komut : chromium --kiosk '--app=http://127.0.0.1:8090/index.html?clientID=…' \
        --user-data-dir=/home/…/kiosk/.tarayici-profil --no-first-run … --window-size=1920,1080
```

Ekranda görmeniz gerekenler: sol panelde nöbetçi listesi (satır yüksekliği 5'li tabana göre
sabit), ortada eczane adı/telefon/adres ve tarih aralığı etiketi, sağ altta saat–tarih–gün,
liste bitince yayın görseli ve altta kırmızı **kayan yazı kuşağı**.

---

## 5) Elle (kiosk olmadan) deneme

Sunucuyu elle başlatıp Chromium ile açabilirsiniz:

```bash
cd kiosk && python3 -c "
from core import tarayici, veri_kaynagi
print(tarayici.url_olustur(veri_kaynagi.client_id()))
import time; s,p,_ = tarayici.sunucu_baslat('127.0.0.1', 8090); time.sleep(3600)"
# başka terminalde:
chromium --app='http://127.0.0.1:8090/index.html?clientID=<cihaz>&veri=yerel'
```

---

## 5.1) Ekran üstü teşhis — `d` tuşu (kiosk modunda konsol yok)

Kiosk modunda geliştirici araçları açılamaz. Cihazda bir sorun görürseniz **klavyeden `d`
(veya `F8`)** tuşuna basın: ekranın sol üstünde durum özeti görünür. Aynı tuşla kapanır.

Rapor şunları içerir: sayfa adresi, `hazır`/`hata` durumu, cihaz kimliği ve veri modu,
eşleşen ilçe/bölge, gün bloğu, kayıt sayısı ve gösterilen kayıt, yayın modu + görsel adresi,
önbellek durumu + `lastupdate` damgası, özellik anahtarları, kuşak metni, saat ve
**son 6 günlük satırı** (hatalar dahil).

Bu satırları fotoğraflayıp paylaşmanız hata ayıklamayı `--tani` raporu kadar kesin yapar.

## 6) Açılışta otomatik başlatma (kiosk cihazı)

`~/.config/systemd/user/yourkiosk.service`:

```ini
[Unit]
Description=yourkiosk (tarayıcı kiosk modu)
After=network-online.target

[Service]
WorkingDirectory=/opt/yourkiosk/kiosk
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
Environment=DISPLAY=:0        # X oturumu (Wayland'de WAYLAND_DISPLAY)

[Install]
WantedBy=default.target
```

---

## 7) Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| **Beyaz ekran**, konsolda `Failed to load module script` / `/src/main.ts` 403 | Arayüz **derlenmemiş** (kaynak klasör sunuluyor) | `cd web && npm install --include=dev && npm run build` (1. adım) |
| **Siyah ekran** (CSS yüklenmiş, arayüz çizilmemiş) | Paket yüklenemedi/çalışmadı; ya da GPU birleştirme sorunu | Önce `python3 tools/tarayici_kiosk.py --tani` çalıştırın: ön kontrol raporu + tarayıcı konsolunu terminale döker. GPU şüphesinde `--disable-gpu` zaten varsayılan |
| **Siyah/beyaz ekran** — hiçbir şey görünmüyor | Arayüz derlenmemiş **veya eski** | `cd web && npm install --include=dev && npm run build` |
| Siyah ekran + `PHONE_REGISTRATION_ERROR` / `DEPRECATED_ENDPOINT` satırları | Chromium'un Google servisleri gürültüsü (zararsız) | Yoksayın; bunlar "açılmama" sebebi değil |
| **Siyah ekran + konsolda HİÇ hata yok** | `yerlesim.json` ölçüleri Qt'den **sayı** gelir; CSS'e birimsiz yazılırsa (`--ekran-y: 1080`) `height` geçersiz olur → `auto` → sahne yüksekliği 0 → arkadaki siyah `body` görünür. Eksik/yanlış anahtar da (`viewport_yukseklik` ↔ `viewport_yuksekligi`) aynı sonucu verir | `cd web && npm run build`. Doğrulama: `d` tuşu ile açılan teşhiste `ölçü: --ekran-y=1080px` yazmalı |
| Adımlar gecikiyor, yayın süresi dolmadan atlanıyor, geçişler takılıyor | Chromium pencereyi "arka planda/örtülü" sayarsa `setInterval`i 1 sn'ye yavaşlatır, `requestAnimationFrame`i duraklatır | Yeni sürümde `--disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows` varsayılan; ayrıca geçişler rAF'a bağımlı değil (yedek zaman aşımı var) |
| Hata kartı: "arayüz başlatılamadı" | Paket 6 sn içinde çizim yapmadı | Karttaki adres/konsol bilgisini paylaşın |
| Görseller gelmiyor, konsolda CORS uyarısı | Tarayıcı farklı alan adındaki görseli `fetch` EDEMEZ (Qt'de bu kısıt yok) | Görseller yerel sunucudan `/gorsel?u=…` köprüsüyle alınır (indirme + doğrulama + cihaz önbelleği sunucuda) — `npm run build` ile arayüzü güncelleyin |
| Konsolda `404 /ayarlar.json`, `404 /kapsam-ayarlari.json` | Bu dosyalar isteğe bağlıdır (panelden yazılır) | Yeni sürümde eksikse **varsayılan ayarlar** 200 ile sunulur; yine de görüyorsa eski derleme |
| Nöbet değişikliği ekranda geç görünüyor | Uzun yoklama ucu çalışmıyor olabilir (eski derleme/statik sunum) | Yeni sürümde: `/degisiklik` ucu + 20 sn damga yoklaması. `d` kaplamasında `anlık bildirim…→yenileniyor` ya da `damga değişti…→yenileniyor` satırı görünmeli. Ayrıntı: `kiosk/NODET-DEGISIKLIGI.md` |
| Nöbetçi listesi/yayın boş, saat var | Veri çözümlendi ama kayıt yok | `--tani` raporu ve karttaki cihaz kimliği eşleşmesini kontrol edin |
| Konsolda `TypeError: n.includes is not a function` / `Veri yüklenemedi` | **Eski derleme**: gerçek `Cache.keys()` string değil **Request** döndürür | `cd web && npm run build` (bu sürümde anahtarlar metne çevrilir) |
| Konsolda `TypeError: Failed to execute 'put' on 'Cache': Request scheme 'meta' is unsupported` | **Eski derleme**: önbellek anahtarları geçerli http(s) adresi olmalı (Cache Storage kuralı) | `cd web && npm run build` (bu sürümde anahtarlar `…/__onbellek/…` biçiminde geçerli URL'dir) |
| "arayüz derlenmemiş" mesajı, çıkış kodu 4 | `web/dist/index.html` yok | 1. adım |
| "tarayıcı bulunamadı" (çıkış kodu 2) | `chromium` PATH'te yok | `chromium` kurun ya da `calistirma.tarayici_yolu` ayarlayın |
| Sayfa geliyor ama **veri yok / hata kartı** ("cihaz kimliği bulunamadı") | `clientID` URL'de yanlış ya da `match.json` içinde yok | `makinebilgileri.json` ve `match.json` kontrol |
| Hata kartı: "Veri okunamadı (lastSystemData.json)" | dosya yok/bozuk | `kiosk/lastSystemData.json` var mı; `veri=https` ise `DOSYA_ADRESI` doğru mu |
| Görsel/yayın gelmiyor | Yayın penceresi kapalı ya da görsel alınamadı | `lastSystemData.json` → `Yayinlar` içindeki `start`/`end` şu anı kapsıyor mu |
| Port dolu uyarısı | 8090 başka serviste | `calistirma.web_sunucu_portu` değiştirin (başka servis ise başlatıcı boş port seçer) |
| Tarayıcı açılıp hemen kapanıyor | `yeniden_baslat_s = 0` | 5 saniye yapın; tekrarlı çökmede 60 sn'de 5 denemede vazgeçilir |

Yararlı doğrulamalar:

```bash
cd kiosk
python3 tools/tarayici_kiosk.py --kuru                       # adres/komut
python3 -c "from core import tarayici; print(tarayici.derlenmis_mi(), tarayici.web_kok())"
grep -E "gösterim modu|web sunucu|tarayıcı" kiosk/kiosk.log | tail -5
cd ../web && npm run test                                    # 86 test (arayüz)
```

---

## 8) Güvenlik ve kaynak kullanımı

* Yerel sunucu **yalnızca 127.0.0.1**'i dinler; `..`/sembolik bağ reddedilir, dizin listesi yoktur.
* **Cihaz kimliği hiç sunulmaz** (`makinebilgileri.json` → 403); kimlik URL'den gelir.
* Sunulan veri: `lastSystemData.json`, `lastupdate.json`, `match.json`, `sablon.json`,
  `ayarlar.json`, `kapsam-ayarlari.json` + `bg_layout/*.png`, `logo.png`.
  Cihazda **bulunmayan** isteğe bağlı ayar dosyaları 404 yerine **varsayılan içerikle** sunulur.
* **Görsel köprüsü `/gorsel?u=<adres>`:** tarayıcı farklı alan adındaki görseli `fetch`
  edemez (CORS), bu yüzden görseli **sunucu** indirir. Aynı kapıdan geçer: izinli alan adı
  listesi, yalnız HTTPS, bayt/piksel bütçesi, biçim beyaz listesi (SVG/HTML reddedilir).
  İndirilen görsel **Qt ile aynı cihaz önbelleğine** (`kiosk/onbellek/gorsel/`) yazılır →
  ikinci gösterimde ağa hiç çıkılmaz. Köprü **açık proxy değildir**: izin listesi dışı
  adres 403 döner.
* Kalıcı Chromium profili (`kiosk/.tarayici-profil/`) veri önbelleğini taşır —
  **incognito kullanılmaz**; bu yüzden veri ikinci açılışta internetten gelmez.
* Veri kuralları Qt ile aynıdır: `lastupdate` değişmediyse büyük dosya indirilmez; süresi geçen
  görseller (yayının `end` + `onbellek.gorsel_saklama_gun`) cihazdan silinir. Yayın verisi
  sunulurken önbellek bakımı otomatik çalışır.

### Veri dosyaları yok (temiz klon) — "Nöbet verisi bulunamadı: lastSystemData.json"

Depo cihaz verisini **içermez** (`lastSystemData.json`, `match.json`, `lastupdate.json`,
`makinebilgileri.json` `.gitignore`'da). Temiz klonda tarayıcı modu açılır ama veri kartı çıkar;
`--tani` raporu da "cihaz verisi : EKSİK" der. Düzeltme:

```bash
# cihazda bir kez: veriyi kaynaktan üret (kimlik yoksa --cihaz-id ile oluşturulur)
python3 tools/fetch_nobet.py --cihaz-id <clientID>
# ortamı denetle (traceback yerine ne yapılacağını söyler):
python3 tools/fetch_nobet.py --kontrol

# ya da eski kurulumdan kopyala:
cp /eski/kurulum/kiosk/{lastupdate,lastSystemData,match,makinebilgileri}.json kiosk/
```
