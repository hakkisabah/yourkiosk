# Sıradaki işler (güncel plan)

> 19 Kasım 2026 — eski `otomasyon/` arşivi ve kök belgeler okunarak güncellendi.
> Yeni uygulama `agents/` altındadır; eski Hermes/otomasyon kodu arşivdedir
> (`~/.config` dışında, `agents-test/arsiv`).

## Zorunlu iş akışı (değişmez)

Üç makine yalnız **GitHub** üzerinden konuşur; açık port yok:

1. **Geliştirici (aceri5):** dal + commit + PR açar; kendi işini onaylamaz.
2. **i5 (güvenlik):** PR'ın head commit'ini inceler → `guvenlik/inceleme` durumu + ayrıntılı
   PR yorumu + `guvenlik/onay` / `guvenlik/sorun` etiketi.
3. **i3 (karar):** i5 onayını ve bulguları doğrular → `guvenlik/karar` + gerekirse
   `karar/verildi` / `duzeltme/gerekli`; yalnız çift onayda squash merge.

Zorunlu kontroller: **`guvenlik/inceleme` + `guvenlik/karar`**; ikisi `success` olmadan merge yok.
> **Mevcut durum:** `main` korumasında yalnız `guvenlik/inceleme` zorunlu; `guvenlik/karar`ı
> eklemek **Administration: RW** token gerektiriyor (ajan token'larında yok). Admin token gelince
> iki kontrol de zorunlu yapılacak.
Karar JSON'u: `makine`, `pr`, `sha`, `karar`, `onem`, `ozet`, `bulgular` (dosya:satır + kabul),
`denetlenen` (i5: 12 alan), `nonce`. Kararsızlıkta **onay verilmez** (fail-closed).
Makine kimliği root sahipli `/etc/yourkiosk-makine-kimligi` ile doğrulanır.

## Durum

- Yorum + etiketler çalışıyor: PR #118, #120 doğrulandı (i5 yorumu, `guvenlik/onay`,
  `karar/verildi`); aynı SHA için yorum tekrarı engellendi (#121).
- Lambda kodu hazır: `POST /komut` (HMAC imza), `POST /veri-guncelle` + EventBridge,
  panelde "Komut gönder" / "Veriyi güncelle" butonları. **AWS'ye deploy edilmedi.**
- Kiosk testleri **662**, panel **290**, lambda **31**, agents **22** (son doğrulanan).

## Kalan işler

1. **Canlı cihaz doğrulamaları** (fiziksel cihaz):
   - `kiosk/tools/gecici_coklu_test.py --adet 8` → 8 satır + kaydırma + alt şerit temiz;
     `--geri-al` sonrası eski görünüm.
   - `kiosk/tools/nobet_tetikle.py` → tarayıcıda ≤1 sn, Qt'de ≤20 sn; kapsam dışı ilçe etkilenmez.
2. **Lambda deploy + AWS izinleri** (S3 okuma/yazma, Lambda, IAM PassRole):
   - `/komut`: `KOMUT_ANAHTARI` (cihazdaki `komut.anahtar` ile aynı) → `komut.json`.
   - `/veri-guncelle`: kaynaktan nöbet verisini çekip `lastSystemData.json` + `lastupdate.json`.
   - EventBridge saatlik kural; panel env `KOMUT_ANAHTARI`.
3. **İş 4 — ölçüm/belge:** tarayıcı modu bellek + ağ trafiği ölçümü; README ekran görüntüleri;
   `panel/MAALIYET.md` tetikleyici + 20 sn yoklama maliyeti.
4. **İş 5 — canlıya geçiş:** `deploy/CANLIYA-GECIS.md` sırası (S3 sürümleme/yaşam döngüsü,
   CloudFront 304, panel yayını, cihaz kurulumu, imzalı güncelleme, MQTT cihaz kimliği,
   yedek tatbikatı, CloudWatch alarmları).
5. **MQTT/izleme:** Lightsail + Mosquitto, panel `VITE_MQTT_*`, cihaz başına kimlik,
   600 cihaz çevrimiçi durum doğrulaması.
6. **Panel MFA (TOTP)** ve Telegram bildirimleri (opsiyonel, planlı).

## Ajan sistemi notları

- Kurulum: `python3 agents/install/wizard.py`; config `~/.config/agents/<instance>.toml`.
- Servisler: `agents@<instance>-{developer,reviewer,decision}.service`.
- Reviewer/decision token'larında **Issues: Read and write** + **Commit statuses: RW** zorunlu;
  yoksa yorum/etiket 403 döner.
- Karar ajanı `guvenlik/karar` durumunu **merge'den önce** yazar; zorunlu kontrol merge'i kilitlemesin.
