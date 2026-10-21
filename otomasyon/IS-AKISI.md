# Çok makineli iş akışı — geliştirici (ben) · i5 güvenlik · i3 karar

Bu belge, üç makinenin **birbirine doğrudan bağlanmadan**, yalnız **GitHub üzerinden** haberleştiği
iş akışını tanımlar. Amaç: her commit güvenlik incelemesinden geçsin, sorun varsa ikinci bir makine
karar versin, sonuç bana (geliştirici) **yapılandırılmış bir not** olarak ulaşsın.

## 0. Güncel durum (21 Ekim 2026)

| Adım | Durum |
|---|---|
| Depo görünürlüğü | **public** (private'da branch protection ve secret scanning ücretli) |
| Branch protection (`main`) | ✅ PR zorunlu, force-push/silme kapalı, doğrusal geçmiş, `enforce_admins` |
| Zorunlu kontrol `guvenlik/inceleme` | ⏳ i5 ilk kez çalıştıktan sonra eklenecek (şimdi eklersem hiçbir PR birleşemez) |
| Secret scanning + push protection | ✅ açık |
| Dependabot | ✅ alerts + security updates açık (8 uyarı raporlandı — token'da *Dependabot alerts: Read* yok, triyaj bekliyor) |
| Etiketler | ✅ 4 etiket hazır |
| `yaz.py` yazma yolu | ✅ gerçek yazma doğrulandı (HTTP 201) |
| **Uçtan uca i5 denemesi** | ✅ PR #5 üzerinde: commit durumu `guvenlik/inceleme=success`, PR yorumu, `guvenlik/onay` etiketi — hepsi API'den doğrulandı |
| PR açma | ✅ (`Pull requests: write` eklendi) |
| PR **birleştirme** (API) | ⏳ `Contents: Read and write` gerekiyor; şimdilik arayüzden 1 tık |
| Dependabot | ✅ **0 açık uyarı** (vitest 4.1.12 ile 8 uyarı kapandı) |
| i5 / i3 kurulumu | ⏳ token izinlerine `Pull requests: RW` eklenmeli, sonra cron |

## 1. Neden GitHub "otobüs" olarak seçildi

| Seçenek | Sorun |
|---|---|
| Makineler arası doğrudan bağlantı (SSH/HTTP) | NAT, sabit IP yok, port açmak gerekir, makine kapalıyken mesaj kaybolur |
| Paylaşılan klasör / e-posta | Durum takibi yok, kim hangi commit'i inceledi belirsiz |
| **GitHub (commit durumu + PR yorumu + etiket)** | Kalıcı kayıt, kimlik doğrulamalı, ücretsiz, gecikme yok, makine kapalıysa mesaj **kuyrukta bekler** |

Karar: **tek veri yolu GitHub**. Makineler yalnız `git fetch` + birkaç REST isteği yapar; aralarında
açık port yok.

## 2. Roller

| Makine | Rol | Yapar | Yapmaz |
|---|---|---|---|
| **Bu makine (ben)** | Geliştirici | Kod yazar, dal açar, PR açar, düzeltir, birleştirir | Kendi işini onaylamaz |
| **i5** | Güvenlik incelemesi | Yeni commit'i inceler, `guvenlik/inceleme` durumunu + PR yorumunu yazar | Kod değiştirmez, birleştirmez |
| **i3** | Karar / ikinci görüş | i5'in "sorun" bulduğu değişiklikte karar verir (`duzeltme` / `kabul`) + numaralı plan | Kod değiştirmez, birleştirmez |

## 3. Akış

```
ben: dal + commit + PR
   │
   ├──► i5 (her 15 dk): topla.py → diff + otomatik tarama (sır/riskli kod)
   │        ├── temiz  → commit durumu = success  + etiket guvenlik/onay  + PR yorumu
   │        └── sorun  → commit durumu = failure  + etiket guvenlik/sorun + PR yorumu
   │
   ├──► i3 (her 30–60 dk): yalnız `guvenlik/sorun` etiketli PR'lar
   │        ├── risk gerçek → karar=duzeltme → etiket duzeltme/gerekli + numaralı plan (PR yorumu)
   │        └── risk kabul → karar=kabul    → etiket karar/verildi
   │
   └──► ben: PR yorumundaki JSON bloğu + "Geliştiriciye not" alanını okur, düzeltir, yeni commit atar
            └──► döngü baştan (i5 yeni commit'i inceler)
```

Birleştirme koşulu: `guvenlik/inceleme = success` **ve** onay (branch protection). i5 kapalıysa
birleştirme **bekler** — bu bilinçli: güvenlik kapısı atlanamaz.

## 4. Haberleşme biçimi (makine-okunabilir)

Her yorumun sonunda `<details>` içinde şu blok bulunur (insan için üstte özet + tablo):

```json
{"makine":"i5","karar":"sorun","onem":"orta","sha":"abc1234","pr":12,"bulgu_sayisi":3,"durum":"failure"}
```

- **Etiketler** (durum makinesi): `guvenlik/onay`, `guvenlik/sorun`, `karar/verildi`, `duzeltme/gerekli`.
- **Commit durumları**: `guvenlik/inceleme` (i5), `guvenlik/karar` (i3) — GitHub arayüzünde PR'ın
  altında yeşil/kırmızı nokta olarak görünür.
- i3, i5'in raporunu **yorumdan** okur (ek kanal gerekmez).

## 5. Maliyet ve düşük donanım

| Kalem | Tasarım | Sonuç |
|---|---|---|
| Ağ | `git fetch` (tek) + token varsa **1** API isteği (açık PR listesi) | i5/i3 için günde birkaç yüz KB |
| API | Karar başına 1 durum + 1 yorum + ≤2 etiket = ~4 istek | GitHub limitinin çok altında |
| Model | **Değişiklik yoksa model hiç çağrılmaz** (`degisiklik: false` → çık) | boşta maliyet ≈ 0 |
| Diff | 120 KB'a kırpılır; kilit dosyaları/ikili dosyalar atlanır | i3'te de çalışır |
| Depo | Tam klon gerekmez, `git fetch` yeterli; Node/Python kurulumu **gerekmez** | yalnız `git`, `python3`, `curl` |
| Süre | Koşu başına ~10–60 sn (model hariç) | i5'te 15 dk aralık sorunsuz |

## 6. Senden gerekenler (kontrol listesi)

1. **İki ayrı token** (biri i5, biri i3 — aynı token'ı paylaşmayın, biri sızarsa diğerini etkilemesin):
   - i5 ve i3 için: `Metadata: R` (zorunlu) · `Contents: Read` · `Pull requests: Read and write` ·
     `Issues: Read and write` · `Commit statuses: Read and write`
   - **Administration izni VERMEYİN** (branch protection kurmak benim token'ımın işi).
   - **Benim token'ım** ayrı: `Administration: Read and write` (kurulum sonrası iptal edilebilir).
2. Her makinede token dosyası: `~/.config/hermes-secrets/github-yourkiosk.token` (0600).
3. Her makinede depo klonu: `git clone https://github.com/hakkisabah/yourkiosk.git ~/calisma_konumun/yourkiosk`
   (HTTPS + token ya da o makineye özel deploy key).
4. Her makinede **Hermes cron görevi** (dashboard → Cron ya da o makinedeki Hermes'e "şu görevi kur"
   deyin): i5 `*/15 * * * *`, i3 `*/30 * * * *`; istem = `otomasyon/prompt/i5-guvenlik.md`
   (sırasıyla `i3-karar.md`) içeriği + "önce `topla.py` çalıştır".
5. Bilgi olarak: o makinelerde `python3`, `git`, `curl` var mı? (yoksa: `sudo apt install -y python3 git curl`)
6. Karar: **depo private kalsın mı?** (kalırsa GitHub'ın ücretsiz secret scanning'i yok — i5'in
   regex taraması devrede; public olursa push protection ücretsiz açılır).
7. Saat dilimi/çalışma saatleri: gece de incelensin mi? (öneri: 07:00–23:00 arası, `*/15`)
8. i5/i3'te hangi model bağlı (ucuz model yeterli: diff incelemesi kısa; pahalı modele gerek yok).

## 7. Devreye alma sırası

1. **Ben**: branch protection + etiketler (token gelince) — bu belgeyle birlikte hazır.
2. **Sen**: i5 token'ı + klon + cron → bir sonraki commit'imde ilk yorumu görürsün.
3. **Sen**: i3 token'ı + klon + cron → i5 "sorun" dediğinde i3 devreye girer.
4. **Ben**: `guvenlik/inceleme` durumunu **zorunlu kontrol** olarak branch protection'a eklerim
   (i5 en az bir kez çalıştıktan sonra; öncesinde eklersem PR'lar hiçbir zaman birleşemez).
5. İlk hafta gözlem: yanlış alarm oranı yüksekse `prompt/i5-guvenlik.md` kurallarını sıkılaştırırız.

## 8. Bilinen sınırlar (dürüst liste)

- i5/i3 **kodu çalıştırmaz** (test/pip/npm yok) — inceleme statiktir; derleme/test doğrulaması
  bende kalır (temiz klonda `npm run build` gibi).
- Sır sızıntısı taraması regex tabanlıdır; `gitleaks` kuruluysa `topla.py` yine de regex kullanır
  (ek bağımlılık istemedik). İstenirse `gitleaks detect` çağrısı eklenebilir.
- Aynı commit'e iki makine aynı anda yazarsa son yazan kazanır (yorum üzerine yazılır) — kabul
  edilebilir; kararlar commit durumunda ayrı bağlamlarda tutulur (`guvenlik/inceleme` ≠ `guvenlik/karar`).
- GitHub Actions **kullanılmıyor**: özel depoda dakika kotası ve sır yönetimi ek yük; kendi
  makineleriniz zaten boşta.
