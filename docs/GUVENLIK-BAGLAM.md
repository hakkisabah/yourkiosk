# GÜVENLİK BAĞLAMI — denetçi ajanlar için (i5 / i3)

Bu dosya, güvenlik incelemesi yapan ajanın **proje gerçeğini** bilmesi için var. Genel "iyi
pratikler" listesi değil; bu depoya özgü güven sınırları, otomatik-red kuralları, önem eşikleri ve
**bilerek kabul edilmiş** riskler burada.

Okuma sırası: `AGENTS.md` → bu dosya → `otomasyon/prompt/<rol>.md` → PR'ın kendisi.

## 1. Güven sınırları (bölgeler)

| # | Bölge | Kim erişir | İçinde ne var | Sınır ihlali ne demek |
|---|---|---|---|---|
| A | **Kiosk cihazı** (eczane, fiziksel) | Müşteri/çalışan ekrana bakar; ağ erişimi kısıtlı | Qt uygulaması, yerel önbellek (`~/.cache`), `ayarlar.json`, `komut.json` | Ekranda keyfî kod/içerik, dosya sistemi erişimi, ağdan gelen imzasız komut |
| B | **Panel tarayıcısı** (yönetici) | Tek yönetici hesabı (Cognito, e-posta+parola; TOTP hazır/var) | S3'e yazma yetkisi (Cognito identity → rol), tüm yayın verisi | Sır ifşası, yetki yükseltme, yayın verisinin bozulması |
| C | **Yayın yolu** (S3 + CloudFront) | CloudFront OAC → S3 özel kova; cihazlar `d2dnrvsx5eevod.cloudfront.net/kiosk/...` okur | `durum.json`, `ayarlar.json`, yayın görselleri | Kova public olması, önbellek zehirlenmesi, imza/ETag zayıflatma |
| D | **Operasyon** (mosquitto, Lambda köprüsü, systemd) | Cihaz başına MQTT hesabı; ACL dosyaları | "şimdi güncelle" dürtmesi, cihaz durumu | `allow_anonymous`, geniş joker ACL, parolanın istemciye gömülmesi |
| E | **Otomasyon** (bu makine) | Hermes ajanı, `~/.config/hermes-secrets/github-yourkiosk.token` | PR inceleme/karar, commit durumları | Ajanın kendi işini onaylaması, token'ın loglanması |

Bir bulgu yazarken **hangi bölge** olduğunu söyle: "B bölgesi, panel tarayıcısı, herkes okuyabilir"
gibi. Bölge yazılmamış bulgu kanıtsız sayılır.

## 2. Projeye özel OTOMATİK-RED (kanıt varsa tartışmasız `red`)

Aşağıdakilerden biri varsa karar `red`'dir; "düşük önem" verilmez:

1. Sır (token, parola, API anahtarı, MQTT parolası, özel anahtar) **depoya** ya da `VITE_*`/
   `NEXT_PUBLIC_*` üzerinden **pakete** girmiş.
2. Kiosk cihazında **imzasız** uzaktan komut yolu (`komut.json` HMAC doğrulaması kaldırılmış/
   zayıflatılmış, `komut.anahtar` depoya girmiş).
3. Panelde **kimlik doğrulaması olmadan** yazma (Cognito kapalı, IAM rolü `s3:*` ya da
   `Principal: "*"`, kova public).
4. Kullanıcı girdisiyle **keyfî komut/kod** (`shell=True` + girdi, `eval/exec`, `pickle.loads`,
   doğrulanmamış yol birleştirme ile `..` geçişi).
5. TLS doğrulamasının kapatılması (`verify=False`) ya da `http://` üzerinden sır taşınması
   (localhost hariç).
6. Veri kaybı riski: yayın verisini atomik olmayan yazma, yedek/geri dönüş yolunun kaldırılması,
   silme işleminin onaysız otomatikleşmesi.

## 3. Önem eşikleri (sayısal — "bence orta" yok)

| Önem | Ölçüt |
|---|---|
| `yuksek` | Yukarıdaki 1–6'dan biri **ya da** 600 cihazın tamamını aynı anda düşürecek hata (retry fırtınası, sabit gecikmeyle eşzamanlı yeniden bağlanma), ya da sır ifşası ihtimali |
| `orta` | Tek cihazı/tek oturumu bozan, ya da maliyeti ölçülebilir biçimde artıran (ör. önbellek devre dışı → istek ×N), ya da doğrulama eksik ama sömürü için ek koşul gereken |
| `dusuk` | Davranış doğru, belge/yorum/test tutarsız; ya da sertleştirme önerisi |

**`yuksek` bulgu varken `onay` verilemez** (karar kapısı bunu reddeder).

## 4. Fail-closed kuralı (kararsızlık yasağı)

Emin değilsen **`onay` verme**: `sorun` + `onem: dusuk` + "doğrulanmalı" notu yaz ve neyi
doğrulayamadığını söyle. `karar_dogrula.py` özet/notta "emin değilim", "doğrulanmalı",
"karar veremedim", "şüpheli" gibi ifade görürse `onay`/`kabul` kararını **reddeder**.

Sebep: sessiz belirsizlik zamanla "onay"a dönüşüyor; yanlış onay, gecikmiş incelemeden pahalıdır.

## 5. Kayıtlı kabul edilmiş riskler (tekrar `red` verme)

Bunlar bilerek kabul edildi; **aynı gerekçeyle yeniden bulgu yazma**. Kötüleşirse (kapsam
genişlediyse, yeni sır eklendiyse, koşul değiştiyse) `sorun` ver ve farkı yaz.

| Risk | Gerekçe / plan | Kayıt |
|---|---|---|
| Panel TOTP/MFA **varsayılan kapalı** | Tek yönetici hesabı; altyapı hazır, açmak tek env (`VITE_MFA_AKTIF=1`). Açılana kadar parola + Cognito kaba kuvvet koruması geçerli | `panel/README.md` §6 |
| Kiosk önbelleği **512 MB** üst sınır | Cihaz diskini korumak için; kota aşımında en eski kullanılan silinir. Daha büyük kota **yeni** risk değil, ayar | `kiosk/core/onbellek.py` (`ONBELLEK_MAKS_BAYT`) |
| Yayın görselleri 30 günde silinir (S3 yaşam döngüsü) | Maliyet; görsel 30 günden eskiyse cihaz yer tutucuya düşer | `panel/infra/s3-lifecycle.json`, `docs/AWS-KURULUM.md` |
| Hermes API anahtarı **docker0 köprüsünde** düz `http://` ile taşınır | `172.17.0.1` fiziksel ağ kartı değil, bu makinenin köprü arayüzü: paket makineden çıkmaz, LAN'a görünmez; uç yalnız konteynerden erişilir. TLS sonlandırmak konteyner↔ana makine içi ek altyapı demekti (ölçek: 1 makine, 1 istemci). **Koşul:** `API_SERVER_HOST` beyaz listede kalmalı (`127.0.0.1`/`172.17.0.1`/`172.18.0.1`); `0.0.0.0` ancak `--kabul-et-lan` ile. Anahtar bir ağdan (LAN/tünel) geçecekse TLS vekili zorunlu | `otomasyon/betik/api-sunucu-sertlestir.sh`, `docs/API-SUNUCU.md` §3 |
| Open WebUI arayüzü `127.0.0.1:3000`'de, imaj **sabit etiketle** | Panel benzeri bir yönetim arayüzü; LAN'a açmak kimlik avı yüzeyi. `:main` etiketi sabitlenmediyse denetlenmemiş kod riski → etiket sabitleme operatör adımı | `docs/API-SUNUCU.md` §3 |

Yeni bir riski kabul ediyorsan bu tabloya **PR ile** satır ekle (gerekçe + dosya referansı).
Tabloya eklenmemiş her şey tartışmaya açıktır.

## 6. Bilinen tuzaklar (yanlış bulgu üretme)

- **Bayat sayılar:** süre/sınır sabitleri kodda tek yerde tanımlı; doküman farklı sayı yazıyorsa
  bulgu dokümanındır, kodu değil (`kiosk/core/config.py`, `kiosk/core/timer_manager.py`).
- **`getattr(config, "...", varsayılan)`**: varsayılan değer koddaki ayarla aynı olmalı; test
  ifade biçimini (`1800 * 1000` gibi) göremiyorsa test eksiktir, davranış değil.
- **"behind" dal:** bir PR birleşince diğerleri geride kalır; bu güvenlik bulgusu değil, süreç
  notudur (`dal güncellenmeli` yorumu).
- **Draft PR** inceleme kapsamı dışıdır.
- **`node_modules/`, `dist/`, `.venv/`** içindeki dosyalar bulgu kaynağı değildir.
- **`main` ucunu incelemek** PR'ı "Expected" bırakır: durum **head commit**'e yazılmalı.
- **Sır maskesi yanılgısı:** araç çıktısı `Authorization: Bearer ***` gibi maskelenmiş görünebilir;
  bu bir bulgu DEĞİLDİR. Dosyanın ham baytına bakmadan (`od -c` / `grep -c 'Bearer \$'`) "sabit
  dize gönderiliyor" demeyin — 26 Ekim'de bu yüzden yanlış bir `orta` bulgu yazıldı ve geri alındı.

## 7. Kanıt standardı

Her bulgu: `dosya:satır` + **neden sömürülebilir** + **somut düzeltme** + bölge (A–E).
`karar_dogrula.py` her `dosya:satir`'ın PR head'inde gerçekten var olduğunu, satır numarasının
dosya sınırında kaldığını ve **kararın sha'sının PR'ın güncel head'i olduğunu** ağdan doğrular;
uydurma satır numarası veya bayat sha kararı yayınlatmaz. Kanıt katmanı çalışamıyorsa (token yok)
kapı **fail-closed** davranır: karar geçmez.

## 8. Bu dosyayı kim günceller

- Geliştirici (ben): normal PR ile.
- i5/i3: **yazmaz**, ama eksik/yanlış bağlam görürse karar `not` alanında "bağlam güncellenmeli:
  …" diye ister. Bu istek, bulgu değil süreç notudur.
