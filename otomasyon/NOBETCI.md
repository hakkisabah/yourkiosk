# Nöbetçi — olay güdümlü i5/i3 (cron yerine)

## Neden değişti

| | Eski (cron 30 dk) | Yeni (nöbetçi) |
|---|---|---|
| Gecikme | 0–30 dakika | **≤ 15 saniye** |
| Boşta oturum | Her turda bir oturum (iş olmasa da) | **0** |
| İş başına oturum | Her tur ayrı | Olay başına **1** (tur içinde tüm PR'lar) |
| 7/24 | cron çalışıyorsa | systemd `Restart=always` + `enable-linger` |
| Maliyet | Boş turlar token/oturum üretir | Boşta yalnız 304 yanıtı (ücretsiz) |

## Nasıl çalışır

```
[GitHub]  ←  ETag/If-None-Match (15 sn)  ←  nobetci.py --rol i5
   │                                              │
   │ değişiklik varsa                             │ iş listesi boş → uyu (0 oturum)
   ▼                                              ▼
açık PR'ların head sha + durum kontrolleri   iş listesi dolu → TEK `hermes chat --oneshot`
                                                  → listedeki tüm PR'lar işlenir
                                                  → yaz.py ile durum/yorum/etiket
```

- **i5** işi: `guvenlik/inceleme` kararı **yazılmamış** (`success`/`failure` dışında: hiç yok,
  `pending`, `error`) PR'ları inceler.
- **i3** işi: i5 onayı (`guvenlik/inceleme=success`) olup **kararı yazılmamış** PR'lara karar verir,
  `--birlestir --cift-onay` ile birleştirir.
- **Sıra: EN ESKİ PR ÖNCE.** GitHub listesi yeniden-eskiye döner; bunu olduğu gibi almak 25 Ekim'de
  #83/#84'ü 10 saat aç bıraktı (araya giren her yeni PR kuyruğun başına geçiyordu). Artık tüm açık
  PR'lar çekilir, yaşa göre sıralanır, `limit` **sonra** uygulanır. 120 dakikayı geçen iş varsa
  günlüğe `AÇLIK:` satırı yazılır.
- Oturum başına PR: i5 → 1, i3 → 3 (`OTURUM_BASI_PR`). Kalanlar bir sonraki turda alınır.
- **Aynı commit'e ikinci karar yazılmaz.** Durum kontrolleri commit'e bağlıdır: bu sha için rolün
  kararı yazılmışsa iş bitmiştir, sıra geliştiricide. Yeni commit → yeni sha → PR kendiliğinden
  geri gelir. Bu kural 25 Ekim'deki iki arızayı kapatır: i3 aynı head'e (cc4e4b81) üç tur üst üste
  "düzeltme" yazdı; i5 kendi "sorun" verdiği sha'yı sonsuz yeniden inceledi (boş oturum = token).
  Atlanan her PR için günlüğe tek satır yazılır: `N PR bu commit için zaten karara bağlı`.
  **Yalnız `success`/`failure` "karar yazıldı" sayılır:** `pending` (ağ kesintisi) ve `error`
  (yaz.py çöktü) karar değildir — yarım kalmış durum PR'ı yeni commit gelmeden kuyruktan
  düşürmemeli (26 Ekim i5 bulgusu).
- **Kapıyı atlamak serbest değil:** `--kapi-atla` dört kapı ister: (1) **operatör ortam anahtarı**
  `YAZ_KAPI_ATLA_ONAY=1` (nöbetçi biriminde tanımlı **değil** → otomatik oturum kendi kendine
  atlayamaz), (2) **operatör bileti** `/run/yourkiosk-kapi-atla.bilet` — root sahipli, dünya-okur,
  grup/dünya-yazılamaz, ≤10 dk, üst dizini root sahipli; (3) `--gerekce "…"` (≥20 karakter),
  (4) `yüksek` önemde bulgu **yokluğu**. Bilet **yolu sabittir**: ne ortam değişkeniyle ne argv ile
  taşınabilir; `/proc`, `/sys`, `/dev` altındaki yollar reddedilir (26 Ekim i5 bulgusu: ajan
  `YAZ_KAPI_ATLA_BILET=/proc/1/stat` verip root sahipli sanal dosyayı bilet gibi gösterebiliyordu).
  Atlama PR yorumunda ve `kapi-red.log`da görünür. Operatör bileti üretir:
  `sudo install -m 0644 /dev/null /run/yourkiosk-kapi-atla.bilet`.
- **Karar kapısı:** ajan `yaz.py` ile yazmadan önce `karar_dogrula.py` şemayı, 12 denetim alanını,
  karar tutarlılığını, `dosya:satır` kanıtını ve **kapanış ölçütünü** (`kabul`: "neyi yapınca bu
  bulgu kapanır") denetler. Geçmezse GitHub'a **hiçbir şey** yazılmaz; reddin izi
  `~/.local/state/yourkiosk-otomasyon/kapi-red.log` dosyasına düşer.
- **Yabancı commit koruması:** `yaz.py --birlestir`, dalın BAŞKA bir açık PR'ın commit'ini taşıyıp
  taşımadığını birleştirme anında denetler (25 Ekim: #89 dalı #88'in commit'ini taşıyordu). Taşıyorsa
  birleştirmez; çözüm rebase.
- İki makine birbirini **commit status** üzerinden görür; ayrı bir kuyruk/veritabanı yok.
- Aynı anda iki nöbetçi çalışmasın diye `flock` kilidi var (`nobetci-<rol>.lock`).

## Neden webhook değil?

Hermes'in webhook altyapısı (`hermes webhook subscribe`, port 8644) **gelen** HTTP isteği ister.
i5/i3 ev/ofis ağında, dışarıdan erişilebilir adresleri yok (NAT). Gerçek push için üç seçenek var:

1. **Tünel** (cloudflared/ngrok) + webhook → en hızlı (~1 sn), ama üçüncü taraf servis + yapılandırma.
2. **Self-hosted GitHub Actions runner** → GitHub işi doğrudan makineye iter (~1–2 sn), gelen port
   gerekmez; kurulum token'ı **GitHub arayüzünden** alınır (Settings → Actions → Runners → New
   self-hosted runner). Genel (public) depoda fork PR'ları makinede kod çalıştırabileceği için
   `if: github.event.pull_request.head.repo.full_name == github.repository` şartı zorunludur.
3. **Nöbetçi (bu çözüm)** → 15 sn gecikme, ek servis yok, NAT sorunu yok, kurulumu 1 komut.

15 saniye, PR akışı için pratikte "anlık" sayılır; bu yüzden nöbetçi varsayılan seçildi.

## Kurulum (her makinede bir kez) — `git pull` YOK

Servis **makineye ait ayrı bir klondan** çalışır: `~/.local/share/yourkiosk-nobetci/depo`.
İnsan deposunun dalı, kirli ağacı ve `.git/config`'teki `[branch]` bölümleri bu işe **karışmaz**.
Sebep gerçek bir arıza: i5'te `git pull` çalışmıyordu (`[branch "x"] merge = refs/heads/baska-dal`),
kod güncellenmedi, makine bellek tavanı olmayan sürümü koştu ve `node-MainThread`
`FatalProcessOutOfMemory` ile core dump üretti.

```bash
# TEK KOMUT (depo eski/bozuk olsa bile çalışır: fetch + show | bash — pull/checkout gerekmez)
git -C ~/projeler/yourkiosk fetch origin main && \
  git -C ~/projeler/yourkiosk show origin/main:otomasyon/betik/nobetci-bakim.sh | bash -s -- i5
```

i3'te aynı komut `i3` argümanıyla. Bakım betiği şunları yapar (hepsi idempotent, sudo **yok**):

| Adım | Ne yapar |
|---|---|
| 1 | Klon yoksa `git clone --branch main`, varsa `fetch` + `reset --hard origin/main` (makine kopyası) |
| 2 | Bellek tavanlarını **drop-in** olarak yazar: `yourkiosk-nobetci.service.d/50-bellek.conf` (RAM'den ölçülür) |
| 3 | Birimi klon yolundan üretir: `--depo <klon> --dal <dal> --guncelle` |
| 4 | Çalışan birime tavanı `set-property` ile **canlı** uygular (oturumu öldürmez) |
| 5 | Oturum içinden çağrıldıysa restart'ı `systemd-run --on-active` ile **geciktirir** |

**Hata görünürlüğü:** bakım betiği artık klondaki `nobetci-kur.sh`ın çıktısını yutmaz. Klondaki kod
makine kopyası + kendini güncelleme biçimini desteklemiyorsa **çıkış 8** ile `DESTEKLEMİYOR` der ve
çözüm komutunu yazar; gerçek kurulum patlarsa alttaki komutun çıktısı **aynen** gösterilir (çıkış 7).
(27 Ekim: `✗ birim kurulumu başarısız` deyip neden yazmıyordu.)

### Düzeltme dalından çalıştırma — `--dal` (kilitlenme çözümü)

Şu kilitlenme gerçek: servis ölü → i5 inceleme yapamıyor → PR'lar birleşemiyor → düzeltme `main`e
giremiyor → servis ölü kalıyor. Bu yüzden bakım betiği **istenen dalı** izleyebilir:

```bash
# düzeltmeyi taşıyan daldan kur (main'e merge edilmeden makine yeni kodu koşar)
git -C ~/projeler/yourkiosk fetch origin <duzeltme-dali> && \
  git -C ~/projeler/yourkiosk show FETCH_HEAD:otomasyon/betik/nobetci-bakim.sh | bash -s -- i5 --dal <duzeltme-dali>
```

İzlenen dal `~/.local/state/yourkiosk-otomasyon/nobetci-dal` dosyasına yazılır; birim `--dal <dal>`
alır; `--guncelle` ve kontrol noktası 13 bu dalı kullanır. **Merge sonrası normale dönmek için**
`bash otomasyon/betik/nobetci-bakim.sh i5` (dal varsayılan `main`).

Sonrasında doğrulama ve günlük:

```bash
(cd ~/.local/share/yourkiosk-nobetci/depo && python3 otomasyon/betik/nobetci.py --rol i5 --kendini-denetle)
bash otomasyon/nobetci-kur.sh i5 --durum        # servis + nöbetçi durumu
tail -f ~/.local/state/yourkiosk-otomasyon/nobetci-i5.log
journalctl --user -u yourkiosk-nobetci -f
```

### Kendini güncelleme (bir daha elle müdahale yok)

Birim `nobetci.py --guncelle` ile çalışır. Nöbetçi **tur arasında** (açık oturum yokken) klonu
`origin/main`e çeker; kod değiştiyse süreç `çıkış 75` ile biter ve `Restart=always` yeni kodu yükler.
Yani bundan sonra bir düzeltme `main`e girdiğinde makinelere kendiliğinden ulaşır. İnsan deposunda
(klon işareti yoksa) yalnız `merge --ff-only` denenir — kimsenin dalı/commit'i ezilmez.

```bash
# makine kopyası mı, kod güncel mi?
python3 otomasyon/betik/nobetci.py --rol i5 --tani      # "kod: <sha> (makine kopyası) · kendini güncelleme: açık"
```

## Ayrı profil (i5 mimarisi — Open WebUI yükünü ayır)

i5 makinesi hem Open WebUI sohbetlerini hem nöbetçiyi çalıştırıyorsa aynı gateway süreci paylaşılır:
aynı CPU, `max_concurrent_runs`, model kotası ve günlük oturum tavanı. Sonuç 25 Ekim'de görüldü
(3 PR tek oturuma, `çıkış 124`, PR'lar saatlerce bekledi). Ayrım:

```bash
hermes profile create guvenlik
hermes -p guvenlik config set platforms.api_server.enabled false   # bu profilde API sunucusu YOK
bash otomasyon/nobetci-kur.sh i5 --profil guvenlik                 # unit: NOBETCI_PROFIL + Nice=10
python3 otomasyon/betik/nobetci.py --rol i5 --tani                 # "hermes profili: guvenlik"
```

Profil yoksa `nobetci-kur.sh` **kurulumu reddeder** (çıkış 3) — sessizce varsayılan profile düşmez.

## Ayarlar

| Ayar | Yer | Varsayılan |
|---|---|---|
| Yoklama aralığı | `nobetci-kur.sh` içindeki `--aralik` | 15 sn |
| Tur başına PR (liste) | `--limit` | 8 |
| Oturum başına PR (işlenen) | `nobetci.py` `OTURUM_BASI_PR` | i5: 1 · i3: 3 |
| Açlık eşiği (günlük uyarısı) | `nobetci.py` `ACLIK_ESIGI_DK` | 120 dk |
| Oturum zaman aşımı | `--zaman-asimi` | 1860 sn (tavan 120 × 15 sn + 60 sn; türetilir) |
| Tur tavanı | `nobetci.py` `OTURUM_TUR_TAVANI` | 120 tur (bütçe darsa kısılır) |
| Günlük oturum tavanı | `nobetci.py` `GUNLUK_OTURUM_TAVANI` | 120 |
| Depo | `Environment=GITHUB_DEPO` | `hakkisabah/yourkiosk` |
| Token | `~/.config/hermes-secrets/github-yourkiosk.token` | — |

## Sorun giderme

| Belirti | Bak |
|---|---|
| Servis düşüyor | `journalctl --user -u yourkiosk-nobetci -n 50` |
| `git pull` "no tracking information" veriyor | artık gerekmiyor — `nobetci-bakim.sh` klonu kendisi çeker (`fetch` + `reset`) |
| Kod güncellenmiyor / makine eski sürümde | `--tani` → `kod:` satırı; `--kendini-denetle` 13–14 ✗ ise `nobetci-bakim.sh` |
| `dumped core` / `FatalProcessOutOfMemory` | birimde + drop-in'de tavan var mı (kontrol 9), boş RAM (10), ağır komut koşucusu (12) |
| "iş yok" ama PR bekliyor | `./otomasyon/betik/nobetci.py --rol i5 --tani` → yaş + sıra |
| PR saatlerdir incelenmiyor | günlükte `AÇLIK:` satırı; `--tani` çıktısında en eski PR'ın `dk açık` değeri |
| Oturum açılıyor ama durum yazılmıyor | `nobetci-i5.log` sonunda oturum çıktısı; `hermes chat -q` çalışıyor mu |
| Aynı PR'a tekrar tekrar oturum | i5 durumu yazamıyor olabilir; `kapi-red.log` + `yaz.py` çıktısına bak |
| Ajan karar yazamıyor | `python3 otomasyon/betik/karar_dogrula.py /tmp/karar-<no>.json` → eksik alan/kanıt |
| Oturum kapanınca duruyor | `loginctl enable-linger $USER` — bazı sistemlerde polkit onayı ister: `sudo loginctl enable-linger $USER` (kurulum betiği uyarı verir, hata değil) |

## Kontrol noktaları (tek komut)

```bash
./otomasyon/betik/nobetci.py --rol i5 --kendini-denetle     # hiçbir şeyi değiştirmez, ✗ varsa çıkış 1
```

| # | Kontrol | Eşik |
|---|---|---|
| 1 | Projeye ait kalan cron görevi | 0 |
| 2 | systemd servisi | `active` |
| 3 | `linger` | açık |
| 4 | Durum dosyası tazeliği | < 60 dk |
| 5 | Bugünkü oturum | ≤ 24 |
| 6 | **En eski iş yaşı** (kuyruk tıkanıklığı) | < 120 dk |
| 7 | Son 24s zaman aşımı (`çıkış 124`) | 0 |
| 8 | Son 24s karar kapısı reddi | < 3 |
| 9 | **Bellek tavanı birimde** (`MemoryMax` + `NODE_OPTIONS` heap) | tanımlı |
| 10 | **Boş RAM / takas** | ≥ 500 MB boş · takas <%50 |
| 11 | **Son 24s OOM / core dump izi** | 0 (`journalctl --user -u …`) |
| 12 | Ağır komut koşucusu (`agir-komut.sh`) | var + çalıştırılabilir |
| 13 | **Kod `origin/<izlenen dal>` ile aynı** (eski kod = eski hata) | eşit sha |
| 14 | **Kod deposu makine kopyası** (insan deposu değil) | klon işareti var |

## Bellek tavanı (26 Ekim dersi — node core dump)

**Belirti:** `journalctl --user -u yourkiosk-nobetci` içinde

```
Process 101636 (node-MainThread) of user 1000 dumped core.
#3  node::OOMErrorHandler … #5 v8::internal::Heap::FatalProcessOutOfMemory
```

**Kök neden:** makinede ~3,8 GB RAM var; V8 tavanını makine RAM'inden **bağımsız** kurar (Hermes TUI
8 GB ister, Node varsayılanı ~2 GB). Ağır bir Node komutu (test/typecheck/derleme) tavansız koşunca
heap makinenin taşıyamayacağı yere ayarlanır → takas dolar → V8 "ölümcül OOM" ile **abort** eder
(çekirdeğin OOM-killer'ı değil, sürecin kendisi). i3'te görülmemesinin nedeni: i3 kod/derleme
koşmaz, yalnız karar verir.

**Dört katmanlı koruma (hepsi birimde/betikte görünür):**

| Katman | Nerede | Ne yapar |
|---|---|---|
| V8 tavanı | birim `Environment=NODE_OPTIONS=--max-old-space-size` | Node çocukları RAM'in 1/4'ü kadar heap ile sınırlanır (4 GB makinede ~950 MB) |
| cgroup tavanı | birim `MemoryHigh` (%60) / `MemoryMax` (%75) | taşma olursa OOM **yalnız birimi** öldürür; makine ve sohbet ayakta kalır |
| Çökme freni | birim `StartLimitIntervalSec=300` + `StartLimitBurst=5` | OOM sonrası `Restart=always` sonsuz oturum/core dump döngüsü kurmaz |
| Ağır komut koşucusu | `otomasyon/betik/agir-komut.sh` | boş RAM eşiği altında **reddeder** (çıkış 7), ölçülü heap verir, `systemd-run --scope` ile yalıtır, `flock` ile sıraya sokar (çıkış 8) |

```bash
# planı gör (hiçbir şey koşmaz)
./otomasyon/betik/agir-komut.sh --kuru -- npm test

# ağır komut (test / typecheck / derleme) — doğrudan `npm test` DEĞİL
cd panel && ../../otomasyon/betik/agir-komut.sh -- npm test
```

**Ölçülen gerçek değerler (bu depoda, boş makinede):** panel `vitest` 576 MB tepe · `vue-tsc`
930 MB tepe · web `vitest` 340 MB tepe. Yani tek komut sığar; **iki ağır komut + sohbet gateway'i**
4 GB'a sığmaz — koşucunun sıraya sokması bu yüzden.

Tavanlar `nobetci-kur.sh` çalışırken makineden ölçülür (sabit sayı yazılmaz); kurulum çıktısı
`bellek tavanı: RAM … MB → MemoryHigh … MemoryMax … heap …` satırını basar. Birim güncellendikten
sonra doğrulama: `python3 otomasyon/betik/nobetci.py --rol i5 --kendini-denetle` → 9–12 ✓.

## Sınırlar

- GitHub API oranı: kimlik doğrulamalı 5.000 istek/saat; koşullu isteklerde 304'ler sayılmaz → 15 sn'de
  bir yoklama ≈ 240 istek/saat (yalnız PR listesi) + PR başına 1 durum isteği (o da ETag'li).
- Nöbetçi **kod yazmaz**; yalnız inceleme/karar/merge yapar (i5 ve i3 promptlarındaki sınırlar geçerli).
- Token'da `Administration` izni yok — gerekmiyor; durum/yorum/etiket/merge için `Contents`,
  `Pull requests`, `Commit statuses`, `Issues` yeterli.
