# Uzaktan komut — yeniden başlat / uygulamayı yeniden başlat / ekranı yenile

Cihazın bulunduğu yere gitmeden **yeniden başlatma** ve **ekran tazeleme** yapabilmek için
sunucudan (S3) gelen, **imzalı** ve **beyaz listeli** bir komut düzeneği vardır.

Komut, panelin yazdığı `komut.json` dosyasıyla taşınır. Panel bugün `durum.json` içine **komut
işareti yazmıyor**; bu yüzden cihaz komut dosyasını **her 10 yoklama turunda bir** yapılan çapraz
kontrolde indirir. Gerçek üst sınır bu yüzden:

* push **bağlı**: 10 × 120 sn = **en çok 20 dakika**
* push **kopuk**: 10 × 30 sn = **en çok 5 dakika**

(İndirme koşulludur — ETag/Last-Modified ile 304 dönerse gövde inmez, maliyet ~0'dır.)
Nöbet tetikleyicisi (`tetikle.json`) ile **aynı** taşıma yolu kullanılır — tek fark, komutun
çalıştırılmadan önce imza denetiminden geçmesidir. Panel `durum.json`a komut işareti yazmaya
başlarsa gecikme `DAMGA_KONTROL_MS`'e (120/30 sn) iner.

---

## 1. Hangi komutlar var?

| Komut | Ne yapar | Varsayılan işlem |
|---|---|---|
| `yeniden-baslat` | Cihazın tamamını yeniden başlatır | `systemctl reboot` |
| `uygulamayi-yeniden-baslat` | Yalnız kiosk uygulamasını/servisini yeniden başlatır | `systemctl restart kiosk.service` |
| `ekrani-yenile` | Ekranı tazeler (tarayıcı modunda sayfa yeniden yüklenir) | (süreç çalışmaz — uygulama içi) |

İşlemler `kiosk/ayarlar.py` → **Çalıştırma** grubunda (`komut_yeniden_baslat`,
`komut_uygulama_yeniden_baslat`, `komut_ekrani_yenile`) ya da panelin Ayarlar ekranında
değiştirilebilir; boş bırakılan işlem **çalıştırılmaz** ve komut reddedilir (`ekrani-yenile`
hariç — o zaten süreç çalıştırmaz).

> **Neden sabit komutlar?** Cihaz, dosyadan gelen **metni** asla komut olarak çalıştırmaz
> (`shell` yok). Dosyadaki ad yalnızca yukarıdaki üç addan biri olabilir ve çalıştırılacak
> `argv` ayarlardan gelir. S3'e yazma yetkisi ele geçse bile cihazda keyfî komut çalıştırılamaz.

---

## 2. İlk kurulum (tek sefer)

### 2.1. Cihazda anahtar üretin

```bash
cd /home/hakkisabah/yourkiosk/kiosk
python3 tools/komut_gonder.py --anahtar-olustur
```

- `komut.anahtar` dosyası **0600** izniyle oluşur ve **depoya girmez** (`.gitignore`).
- Komut aracı ekrana anahtar değerini yazar; **aynı değeri** diğer cihazlara ve sunucu tarafına
  (Lambda ortam değişkeni, ör. `KOMUT_ANAHTARI`) da koyun.
- Panel tarayıcısına anahtarı **koymayın**: panel istemcisi herkese açıktır, sır sızar.

### 2.2. Servis adını doğrulayın

```bash
systemctl list-units --type=service | grep -i kiosk      # gerçek servis adı ne?
```
Ad farklıysa `ayarlar.json` içindeki `calistirma.komut_uygulama_yeniden_baslat` değerini düzeltin.

---

## 3. Komut gönderme

Yönetici makinesinde (anahtarın bulunduğu yer):

```bash
# yalnız bu cihaz
python3 tools/komut_gonder.py --komut uygulamayi-yeniden-baslat --cihaz 98273648723468273

# tüm cihazlar
python3 tools/komut_gonder.py --komut ekrani-yenile

# dosyayı üretmeden yalnız denetlemek için: önce üret, sonra --dogrula
python3 tools/komut_gonder.py --dogrula komut-gonderilecek.json
```

Araç dosyayı imzalar, kendi kendini denetler ve S3'e kopyalama komutunu yazar:

```bash
aws s3 cp komut-gonderilecek.json s3://<KOVA>/kiosk/komut.json
```

Panelin S3 tarayıcısını kullanacaksanız içeriği **`komut.json`** anahtarına yükleyin.

### Cihaz tarafında ne olur?

1. Cihaz (en geç **20 dakika** — push kopuksa 5 dakika; 10 yoklama turunda bir çapraz kontrol) `komut.json`u indirir → `kiosk/komut.json`.
2. `core/komut.py` sırayla denetler: **beyaz liste** → **imza** → **hedef cihaz** → **tek seferlik**.
3. Geçerse komut çalıştırılır ve `komut-durum.json`'a işlenir.
4. Her adım `kiosk.log`'a yazılır (`UZAKTAN KOMUT: ...`).

```bash
tail -f kiosk.log | grep -i komut
python3 tools/komut_gonder.py --durum     # bekleyen komut + son 5 kayıt
```

---

## 4. Güvenlik kuralları (fail-closed)

| Kural | Davranış |
|---|---|
| İmza zorunlu (`komut_imza_zorunlu`) | İmza yok/yanlış → **uygulanmaz**, günlüğe "reddedildi" |
| Beyaz liste | Üç ad dışındaki her şey reddedilir (`rm -rf`, kabuk boru hattı vb. imkânsız) |
| Sabit `argv` | Çalıştırılacak komut ayarlardan gelir; dosyadan metin çalıştırılmaz, `shell` yok |
| Hedef cihaz | `cihazId` doluysa yalnız o cihaz; boş/`*` → tüm cihazlar |
| Tek seferlik | Aynı `id` ikinci kez uygulanmaz (S3'te dosya unutulsa bile) |
| Kuru çalıştırma | `komut_kuru_calistirma: true` → komut yalnız günlüklenir, çalıştırılmaz |
| Zaman aşımı | `komut_zaman_asimi_s` (varsayılan 60 sn) |
| Anahtar | `komut.anahtar` (0600, depo dışı); panel istemcisinde **bulunmaz** |

**İmza neyi kapsar?** `id|komut|cihazId|zaman` alanlarının HMAC-SHA256'sı. Zaman alanı da
imzalandığı için eski bir dosya sonradan değiştirilip "geçerli" gibi gösterilemez.

**Panel neden komut gönderemiyor?** Tarayıcıda imza üretmek anahtarı istemciye koymayı gerektirir.
Bu yüzden panelde komutlar **salt-okunur** gösterilir (dosya var mı, son komut ne oldu) ve gönderme
yönetici aracı ya da sunucu tarafı (Lambda ortam değişkenindeki anahtarla) üzerinden yapılır.
Lambda tarafı eklendiğinde panelden "gönder" düğmesi açılabilir — anahtar istemciye hiç girmez.

---

## 5. Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| `komut REDDEDİLDİ (imza yok (zorunlu))` | Dosya imzalanmamış; `tools/komut_gonder.py` ile üretin |
| `imza var ama cihazda anahtar yok` | Cihazda `komut.anahtar` yok → 2.1'i uygulayın |
| `imza geçersiz` | Panel/Lambda'daki anahtar ile cihazdaki **farklı** |
| `bu komut zaten uygulandı` | Aynı `id`; yeni komut üretin (araç her seferinde yeni `id` verir) |
| `komut başka cihaz için` | `--cihaz` değeri bu cihazın kimliği değil |
| `tanımlı değil (ayarlar)` | `komut_uygulama_yeniden_baslat` boş ya da yanlış |
| Komut hiç görünmüyor | `DOSYA_ADRESI` (Ayarlar → Çalıştırma) tanımlı mı? Cihaz uzak dosyayı ancak o adresten çeker |
| Yeniden başlatma yetkisi reddedildi | Servis kullanıcısının `systemctl reboot` yetkisi yok → `polkit` kuralı gerekir (yetki verilmezse `ekrani-yenile` kullanın) |

---

## 6. Geri alma

```bash
python3 tools/komut_gonder.py --komut ekrani-yenile      # yeni bir komut gönderin (eski id çalışmaz)
rm -f komut.json komut-durum.json                        # cihazı "komut geçmişi yok" durumuna döndürür
```

`komut-durum.json` silinirse **aynı** komut yeniden uygulanabilir — bunu yalnızca bilinçli olarak yapın.
