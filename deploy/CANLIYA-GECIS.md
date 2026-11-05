# CANLIYA GEÇİŞ — sıralı kontrol listesi

Her adımın **kabul ölçütü** var. Bir adım geçmeden sonrakine geçmeyin; sıra, "cihaz eski veri
gösteriyor" sınıfı hataların çoğunu baştan engeller.

Bu belgedeki komutlar `AWS_PROFILE`, `KOVA` ve `CLOUDFRONT_ID` değişkenlerini kullanır:

```bash
export AWS_PROFILE=yourkiosk-yayin
export KOVA=yourkiosk-veri
export CLOUDFRONT_ID=EXXXXXXXXXXXXX
```

---

## 1. Kararlar (koda girmeden önce)

| Karar | Varsayılan | Ne zaman değişir |
|---|---|---|
| Kimlik modu | **Cognito** (User + Identity Pool; tarayıcı geçici anahtar alır) | Sunucu tarafında şifre/oturum denetimi istiyorsanız `VITE_AUTH_MODU=lambda` (bkz. `panel/MAALIYET.md` §2) |
| S3 ön eki | `kiosk/` | Aynı kovada başka bir uygulama varsa |
| Yayın adresi | CloudFront (OAC ile özel kova) | Kova kamuya açıksa CloudFront şart değil (önerilmez) |
| Anlıklık | Yoklama (30–120 sn) | 600 cihaz + gecikme hedefi < 5 sn ise MQTT (bkz. `deploy/mosquitto/`) |
| Cihaz modu | `qt` | Donanım zayıfsa/tek süreç isteniyorsa `tarayici` |

## 2. S3: kova, sürümleme, yaşam döngüsü, CORS

```bash
aws s3api create-bucket --bucket "$KOVA" --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1
aws s3api put-public-access-block --bucket "$KOVA" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket "$KOVA" --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket "$KOVA" \
  --lifecycle-configuration file://deploy/s3/yasam-dongusu.json
```

**Kabul:** `get-bucket-versioning` → `Enabled`; `get-bucket-lifecycle-configuration` → 3 kural.
**Neden:** sürümleme olmadan `deploy/yedek/` tatbikatı anlamsızdır; yaşam döngüsü olmadan eski
sürümler sessizce depolama maliyeti üretir.

## 3. CloudFront (OAC) — yayın ve veri adresi

1. Distribution → Origin: S3 kova (REST endpoint, **OAC** ile imzalı).
2. Cache policy: `durum.json`, `lastupdate.json`, `tetikle.json`, `komut.json`, `ayarlar.json`,
   `kapsam-ayarlari.json` için **TTL 0** (yalnız cihazın koşullu isteği çalışsın; 304 dönebilsin).
3. `lastSystemData.json` için TTL 60 sn + `ETag` korunmalı (cihaz `If-None-Match` gönderir).
4. Cevap başlıkları: `Access-Control-Allow-Origin` **yalnız panel alan adı** (tarayıcı paneli S3'e
   doğrudan erişiyorsa).

**Kabul:** `curl -I https://<dağıtım>/durum.json` → 200 + `ETag`; ikinci istekte
`If-None-Match` ile **304** ve gövde 0 bayt.

## 4. Panel yayını

```bash
cd panel
cp .env.ornek .env.local          # VITE_* değerlerini doldurun (anahtar DEĞİL: Cognito modunda sır yok)
npm ci && npm run build
aws s3 sync dist/ "s3://$KOVA/panel/" --delete --cache-control "public,max-age=300" \
  --exclude index.html
aws s3 cp dist/index.html "s3://$KOVA/panel/index.html" --cache-control "no-store"
aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_ID" --paths "/panel/*"
```

**Kabul:** panel adresi açılıyor, giriş yapılıyor, "Durum" ekranı dosyaları `var` gösteriyor.
`index.html` **no-store** olmalı: aksi hâlde yeni derleme eski JS'e işaret eder (beyaz ekran).

## 5. Cihaz kurulumu (her cihazda bir kez)

```bash
sudo useradd -m -G video,input kiosk
sudo git clone https://github.com/hakkisabah/yourkiosk /opt/yourkiosk
sudo chown -R kiosk:kiosk /opt/yourkiosk

cd /opt/yourkiosk/kiosk
sudo -u kiosk python3 -m venv .venv && sudo -u kiosk .venv/bin/pip install -r requirements.txt
# tarayıcı modu kullanılacaksa: chromium kurulu olmalı + `cd ../web && npm ci && npm run build`

# cihaz kimliği + veri (ilk tur) — fetch_nobet.py kaynağı kocaelieo.org.tr'dir, `--taban` YOKTUR
sudo -u kiosk .venv/bin/python tools/fetch_nobet.py --cihaz-id <CIHAZ_ID>
# veri adresi + izin listesi (`veri.kaynak=https`, `veri.dosya_adresi`, `ag.izinli_hostlar`):
#   --veri-adresi hostu izin listesine ve 443'ü izinli portlara EKLER; --parola-sor parolayı
#   gizli sorar (kabuk geçmişine yazmaz), --dene broker + veri adresini gerçekten dener.
sudo -u kiosk .venv/bin/python tools/push_ayarla.py --broker <broker-adresi> \
  --veri-adresi https://<dağıtım>/ --parola-sor --dene
sudo -u kiosk .venv/bin/python tools/gecici_coklu_test.py --adet 8   # isteğe bağlı duman testi

sudo cp /opt/yourkiosk/deploy/systemd/yourkiosk-kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now yourkiosk-kiosk.service
```

**Kabul:** `systemctl status yourkiosk-kiosk` → `active (running)`; ekranda nöbet listesi;
`kiosk.log` son 50 satırda traceback yok; `tools/canli_test.py` çıkış kodu 0.

## 6. Güncelleme akışı

**Yetki modeli:** ağaç `kiosk` kullanıcısınındır; güncelleme birimi **root**'tur ama yalnız
`systemctl restart` için. Depo işlemleri (git/npm/pip/sağlık testi) betiğin içinde
`runuser -u kiosk` ile ayrıcalıksız koşar ve birim **root'a ait kopyayı** çalıştırır — kiosk
kullanıcısının yazabildiği betik root olarak çalışmaz (yerel yetki yükseltmesi kapanır).
Ayrıntı: `deploy/guncelle.sh` başlığı + `deploy/systemd/yourkiosk-guncelle.service`.

```bash
# 1) betiği ROOT'a ait kopyaya kur (depo TEMİZKEN; kopya kendini yenilemez)
sudo deploy/kur-guncelle-betigi.sh
#    guncelle.sh sonradan değişirse bu adımı YİNELEYİN (deploy adımının parçası).
#    Kopya eskimişse gece koşusu günlüğe "kopya depodaki sürümden farklı" uyarısı yazar.

# 2) birim + zamanlayıcı
sudo cp deploy/systemd/yourkiosk-guncelle.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now yourkiosk-guncelle.timer

# 3) kuru prova + gerçek
sudo /usr/local/lib/yourkiosk/guncelle.sh --kuru     # önce kuru
sudo /usr/local/lib/yourkiosk/guncelle.sh            # gerçek
```

**Kabul:** `journalctl -u yourkiosk-guncelle -n 30` → `✓ güncelleme tamam`. Çalışma ağacı temiz
değilse betik **durur** (çıkış 3) ve hiçbir şey değiştirmez; `--zorla` ile geçilir.
Depo sahibi beklenmedik bir kullanıcıysa çıkış 4, kiosk kullanıcısı yoksa çıkış 5.

**İMZALI ETİKET ZORUNLU (i5 bulgusu 3):** betik `main` ucunu imzasız çekmez. `origin/main`
üzerindeki en yeni `yayin-*` ANNOTATED etiketi `git verify-tag` ile doğrulanır; imza/anahtar yoksa
güncelleme **reddedilir** (çıkış 6) ve günlüğe açık satır yazılır. **İMZALAYANIN KİMLİĞİ de
doğrulanır (27 Ekim i5 bulgusu 5):** `git verify-tag --raw` çıktısındaki `VALIDSIG` parmak izi
ROOT'a ait beyaz liste (`/etc/yourkiosk/yayin-imzaci`) ile karşılaştırılır; uyuşmazsa ya da liste
yoksa güncelleme reddedilir. Yayın akışı:

```bash
# yayın yapan makinede (GPG imza anahtarıyla)
git tag -s "yayin-$(date '+%Y%m%d')" -m "yayın" && git push origin "yayin-$(date '+%Y%m%d')"
# her cihazda BİR KEZ: imza anahtarının AÇIK anahtarını kiosk kullanıcısına kur
sudo runuser -u kiosk -- gpg --import yayin-anahtari.asc
# her cihazda BİR KEZ: İMZALAYAN PARMAK İZİ beyaz listesi (root'a ait, kiosk yazamaz)
gpg --fingerprint --with-colons yayin-anahtari.asc | awk -F: '$1=="fpr"{print $10; exit}'
sudo install -d -m0755 /etc/yourkiosk
echo 'PARMAK_IZI' | sudo tee /etc/yourkiosk/yayin-imzaci   # 40 hex, büyük/küçük harf fark etmez
```

`--kuru` **hiçbir şeyi değiştirmez**: 27 Ekim i5 bulgusuyla `git fetch --tags --prune --force`
kuru koşudan çıkarıldı (yerel etiketleri güncelliyordu). Kuru koşu ELDEKİ yerel etiketlerle
karşılaştırır ve bunu çıktıda yazar; gerçek koşu fetch eder.

**Neden sağlık denetimi:** etiketten güncelleme + derleme başarısız olursa cihaz bir sonraki
açılışta beyaz ekran verir; betik sağlık denetimi geçmezse önceki commit'e döner.

## 7. İzleme

0. **CİHAZ BAŞINA MQTT KİMLİĞİ (zorunlu adım).** Paylaşılan `cihaz` hesabı `durum/<id>`
   konusuna YAZAMAZ (ACL); kalp atışı ve çevrimiçi izleme yalnız cihaz kimliğiyle çalışır.
   Her cihaz için broker'da bir kez:
   ```bash
   sudo deploy/mosquitto/cihaz-ekle.sh C1          # → cihaz-C1 kullanıcısı + parola (bir kez gösterilir)
   ```
   Çıktıdaki `push_kullanici` / `push_parola` cihazın `kiosk/ayarlar.json` → `tetik` bölümüne
   yazılır **ya da** panelde cihaz ayarından gönderilir. Doğrulama:
   ```bash
   # dogrula.sh iki parolayı ZORUNLU ister (`:?`), aksi hâlde 7. kontrole hiç gelmeden çıkar.
   MQTT_PAROLA_PANEL=... MQTT_PAROLA_CIHAZ=... MQTT_PAROLA_IZLEME=... MQTT_CIHAZ_ID=C1 \
     MQTT_CIHAZ_PAROLA=... sudo -E deploy/mosquitto/dogrula.sh
   # 7. kontrol ✓: "cihaz-C1 kalp atışı yazdı, panel-izleme okudu"
   # "? DOĞRULANAMADI" görürseniz parola/ACL hatası var — ✓ saymayın.
   ```
   Kimlik verilmezse kontrol **atlanır** (yanlış ✓ yazmaz) ve panelde o cihaz çevrimdışı görünür.

1. **Çevrimiçi durum** (MQTT varsa): panel → *Cihazlar* ekranında çevrimiçi/çevrimdışı sayaç ve
   cihaz simgeleri. Cihaz 5 dakikada bir retained kalp atışı yayınlar; LWT kopmada `çevrimdışı`
   yazar. Eşik 15 dakikadır (`panel/src/domain/cihazIzleme.ts`).
2. **Ölçek kanıtı**: `kiosk/tools/olcek_test.py --cihaz 600 --aralik 30 --sure 10` (yerel) —
   gerçek adresle koşarsanız bulut isteği üretir.
3. **Fatura/hata alarmları**: `deploy/cloudwatch/` (4 alarm = ücretsiz kotanın 4/10'u).
4. **Panel "Durum"**: dosya boyutları + son değişiklik + son uzaktan komut kartı.

**Kabul:** panelde 600 cihazın tamamı listeleniyor; çevrimdışı sayısı bilinen bakım listesiyle
uyuşuyor; CloudWatch alarmları `OK` (fatura alarmı ilk 24 saatte `INSUFFICIENT_DATA` olabilir).

## 8. Yedek ve geri dönüş

`deploy/yedek/README.md` §1 tatbikatını **canlıya geçişten önce** bir kez yapın ve tabloyu
doldurun. Gerçek kaza adımları §2'de (önce veri, sonra `lastupdate`, sonra "Bildir").

**Kabul:** tatbikat `✓ doğrulandı` satırı + cihazda görünme süresi kaydı.

## 9. Go / No-Go (hepsi işaretlenmeden canlıya alınmaz)

- [ ] S3 sürümleme + yaşam döngüsü doğrulandı
- [ ] CloudFront `durum.json` 304 dönüyor (maliyet kanıtı)
- [ ] Panel girişi + dosya durumları yeşil
- [ ] En az 2 cihazda Qt **ve** tarayıcı modu açıldı, nöbet listesi göründü
- [ ] Panelden "Bildir" → cihaz ≤ 120 sn içinde tazelendi (ölçülen süre yazıldı)
- [ ] Uzaktan komut (`ekrani-yenile`) uygulandı ve ekranda bilgi göründü
- [ ] `guncelle.sh --kuru` ve gerçek güncelleme bir cihazda denendi
- [ ] Cihaz başına MQTT kimliği verildi (`cihaz-ekle.sh`) ve `dogrula.sh` 7. kontrol ✓
- [ ] Çevrimiçi izleme sayaçları doğru (bir cihazı kapatıp çevrimdışına düştüğü görüldü)
- [ ] Yedekten geri dönme tatbikatı yapıldı
- [ ] CloudWatch alarmları kuruldu, SNS onayı verildi
