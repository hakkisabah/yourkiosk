# Kurulum — i5 ve i3 makineleri (adım adım, denenmiş komutlar)

Bu belge **Hermes'in gerçek cron arayüzüne** göre yazıldı (`cronjob_manage` aracı + `hermes cron`
CLI + dashboard). Önceki sürümdeki "Cron → Yeni görev" tarifi eksikti; doğrusu aşağıda.

> **Çalışma konumu:** bu belge depoyu `~/calisma_konumun/yourkiosk` altında varsayar. Farklıysa
> komutlarda yolu değiştirin ve `KIOSK_YOLU` ortam değişkenini ayarlayın.

Her iki makinede de aynı adımlar; yalnız **prompt** ve **zamanlama** farklı.

---

## 0. Ön koşullar

```bash
python3 --version && git --version && curl --version | head -1
# eksikse: sudo apt install -y python3 git curl
```

---

## 1. Token dosyası

Her makineye **kendi** fine-grained token'ı (i5 ve i3 ayrı; bir sızarsa diğeri etkilenmesin).
İzinler: `Contents: Read` · `Pull requests: Read and write` · `Issues: Read and write` ·
`Commit statuses: Read and write` · `Metadata: Read`. **Administration izni vermeyin.**

```bash
mkdir -p ~/.config/hermes-secrets && chmod 700 ~/.config/hermes-secrets
read -rsp "token: " T && printf '%s\n' "$T" > ~/.config/hermes-secrets/github-yourkiosk.token && unset T
chmod 600 ~/.config/hermes-secrets/github-yourkiosk.token

# doğrula (200 beklenir; 404 → token depoya erişemiyor, 401 → geçersiz)
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $(cat ~/.config/hermes-secrets/github-yourkiosk.token)" \
  https://api.github.com/repos/hakkisabah/yourkiosk
```

---

## 2. Depo klonu

```bash
mkdir -p ~/calisma_konumun
git clone https://github.com/hakkisabah/yourkiosk.git ~/calisma_konumun/yourkiosk
```

Depo **public** → **token'sız** klon/fetch yeterli (i5/i3 yalnız okur; yazma API üzerinden yapılır).

> ⚠ **Token'ı uzak adrese gömmeyin** (`https://x-access-token:github_pat_…@github.com/…`): token
> `.git/config` içine **düz metin** yazılır, `git remote -v` çıktısında ve günlüklerde görünür.
> Yanlışlıkla yaptıysanız:
> ```bash
> git -C ~/calisma_konumun/yourkiosk remote set-url origin https://github.com/hakkisabah/yourkiosk.git
> ```
> Token bir yere sızdıysa GitHub → Settings → Developer settings → token → **Revoke** + yenisini üretin.

---

## 2b. TEK KOMUT (önerilen): `otomasyon/kur.sh`

Denetim + sarmalayıcı betikler + cron komutu tek adımda:

```bash
cd ~/calisma_konumun/yourkiosk
bash otomasyon/kur.sh i5          # denetler, ~/.hermes/scripts'i kurar, cron komutunu YAZDIRIR
bash otomasyon/kur.sh i5 --cron   # ayrıca görevi 'hermes cron create' ile oluşturur
```

Tek tek denetlemek isterseniz:

```bash
./otomasyon/kontrol --rol i5
```

Çıktıda her satır ✓/✗ ve **çözüm** içerir (python sürümü, git/curl, depo, token + izinleri, sarmalayıcı
betikler, `hermes` CLI, durum klasörü). Rol seçenekleri: `i5`, `i3`, `kiosk`, `dev`.

### Komutlar (kısa yol)

| Komut | Ne yapar |
|---|---|
| `./otomasyon/durum` | i5/i3 haberleşmesi: son commit'ler, açık PR'lar, kararlar |
| `./otomasyon/kontrol --rol i3 --yazma-dene` | ortam + izin denetimi (Contents yazma dahil) |
| `./otomasyon/koruma --durum` | branch protection'ın mevcut hâli (salt okuma) |
| `./otomasyon/koruma --uygula --kontrol "guvenlik/inceleme,guvenlik/karar"` | korumayı uygula (yönetici token) |
| `./otomasyon/topla --cikti /tmp/paket.json` | bağlam paketi (diff + tarama + PR'lar) |
| `./otomasyon/yaz /tmp/karar.json [--birlestir]` | kararı GitHub'a yaz / birleştir |

> Bu dosyalar `sh` ile de çalışır (`sh otomasyon/durum`). **Python dosyalarını** doğrudan
> `sh otomasyon/betik/durum.py` diye çalıştırmayın — `line 2: main: command not found` alırsınız.

## 3. Betikleri dene (hiçbir şey yayınlamadan)

```bash
cd ~/calisma_konumun/yourkiosk

# a) monitor çıktısı: uzak HEAD sha'sı (tek satır, deterministik)
./otomasyon/topla --imza

# b) bağlam paketi
./otomasyon/topla --cikti /tmp/paket.json
python3 -c "import json;p=json.load(open('/tmp/paket.json'));print('değişiklik:',p['degisiklik'],'| commit:',len(p['commitler']),'| sır:',len(p['taramalar']['sirlar']))"

# c) karar dosyası ŞABLONU (elle JSON yazmayın — bu komut her zaman geçerli dosya üretir)
./otomasyon/yaz --ornek
./otomasyon/yaz karar-ornek.json --kuru     # yayınlamadan göster
```

> **Not (kiosk cihazı):** `fetch_nobet.py` **cihaz** verisi üretir ve `makinebilgileri.json`
> (clientID) ister. Temiz klonda bu dosya yoktur; artık traceback yerine ne yapılacağını söylüyor:
> `python3 tools/fetch_nobet.py --cihaz-id <clientID>` (dosyayı oluşturur) ya da `--kontrol`.
> **i5/i3 makinelerinde `fetch_nobet.py` çalıştırmaya gerek yoktur.**
>
> **Dünkü hata:** KURULUM.md'deki heredoc (`<<'JSON'` içinde `"$(git rev-parse HEAD)"`) geçersiz JSON
> üretiyordu → `yaz.py` "Expecting ',' delimiter" diyordu. Artık `--ornek` ile üretiliyor; ayrıca
> `yaz.py` bozuk JSON'da satır/kolon ve "şablon üret" ipucu veriyor.

---

## 4. Hermes cron görevi (doğru arayüz)

Hermes'te zamanlanmış görev = **`cronjob_manage` aracı** (`hermes cron create|list|edit|run`).
Önemli alanlar:

| Alan | Ne işe yarar | Bizim için |
|---|---|---|
| `schedule` | `30m`, `every 2h`, `0 9 * * *`, ISO | i5: `30m` · i3: `1h` |
| `prompt` | Görevin kendisi (kendi kendine yeterli olmalı) | `otomasyon/prompt/i5-guvenlik.md` içeriği |
| `script` | Her turda çalışır, **stdout'u prompt'a bağlam olarak eklenir** | `otomasyon-topla.sh` |
| `monitor` / `--monitor-script` | Ucuz değişiklik dedektörü: çıktı **aynıysa ajan hiç çalışmaz** | `i5-imza.sh` → tek satır sha |
| `workdir` | Görevin çalışacağı klasör | `~/calisma_konumun/yourkiosk` |
| `deliver` | Sonucun nereye gideceği | `local` (sonuç GitHub'a yazılıyor, sohbete değil) |
| `enabled_toolsets` | Token tasarrufu | `["terminal"]` |

### 4.1. Sarmalayıcı betikler (Hermes `~/.hermes/scripts/` altından çalıştırır)

```bash
mkdir -p ~/.hermes/scripts
K=~/calisma_konumun/yourkiosk/otomasyon/betik

cat > ~/.hermes/scripts/i5-imza.sh <<EOF
#!/usr/bin/env bash
exec python3 "$K/topla.py" --imza
EOF

cat > ~/.hermes/scripts/i3-durum.sh <<EOF
#!/usr/bin/env bash
exec python3 "$K/topla.py" --imza-sorun
EOF

cat > ~/.hermes/scripts/otomasyon-topla.sh <<EOF
#!/usr/bin/env bash
# paketi üretir; stdout'a YALNIZ özet basar (tam paket /tmp/otomasyon-paket.json içinde)
exec python3 "$K/topla.py" --cikti /tmp/otomasyon-paket.json
EOF

chmod +x ~/.hermes/scripts/*.sh
```

> `$K` **mutlak yol** olmalı (yukarıdaki `EOF` tırnaksız olduğu için kabuk genişletir ✓).

### 4.2. Görevi oluştur — Yol A: o makinedeki Hermes'e söyleyin

O makinede Hermes'e (dashboard sohbeti ya da `hermes`) şunu yazın; gerisini kendisi kurar:

> "Şu cron görevini oluştur: adı **i5 güvenlik**, zamanlama **30m**, workdir
> **/home/KULLANICI/calisma_konumun/yourkiosk**, deliver **local**, toolsets **terminal**,
> monitor-script **i5-imza.sh**, script **otomasyon-topla.sh**. Prompt olarak şu dosyanın içeriğini
> kullan: /home/KULLANICI/calisma_konumun/yourkiosk/otomasyon/prompt/i5-guvenlik.md
> Ayrıca prompt'un başına ekle: 'Bağlam paketi /tmp/otomasyon-paket.json içinde; önce onu oku.
> degisiklik=false ise hiçbir şey yapma.'"

i3 için: ad **i3 karar**, zamanlama **1h**, monitor-script **i3-durum.sh**, prompt `i3-karar.md`.

### 4.3. Görevi oluştur — Yol B: CLI

```bash
cd ~/calisma_konumun/yourkiosk
hermes cron create '30m' "$(cat otomasyon/prompt/i5-guvenlik.md)" \
  --name "i5 guvenlik" \
  --workdir "$PWD" \
  --script otomasyon-topla.sh \
  --monitor-script i5-imza.sh \
  --deliver local
```

```bash
hermes cron create '1h' "$(cat otomasyon/prompt/i3-karar.md)" \
  --name "i3 karar" \
  --workdir "$PWD" \
  --script otomasyon-topla.sh \
  --monitor-script i3-durum.sh \
  --deliver local
```

Kontrol:

```bash
hermes cron list            # iki görev görünmeli
hermes cron run <job_id>    # bir kez hemen çalıştır (arka planda)
hermes cron runs <job_id>   # çalışma geçmişi
hermes cron doctor          # yaygın sorunlar
```

### 4.4. Dashboard'dan

`hermes dashboard` → **Scheduled Tasks / Cron** → **New job**. Formda yukarıdaki tablodaki alanlar
vardır (Name, Schedule, Prompt, Script, Monitor, Model, Deliver, Workdir, Toolsets). Dashboard'da
`script`/`monitor` alanları `~/.hermes/scripts/` altındaki **dosya adıyla** seçilir — bu yüzden 4.1
adımını atlamayın.

### 4.5. "Gece de incelensin mi?" ne demek

Kastettiğim: cron görevi **gece de çalışsın mı**? Makineler açık kaldığı sürece çalışır; uyku/oturum
kapanırsa çalışmaz. Buna gerek yok: gece commit atmıyorsanız i5'in koşması boşuna uyandırma olur.
**Öneri:** i5 `30m`, i3 `1h`; gece de açık kalsın isterseniz hiçbir şey değiştirmeyin (maliyet ~0,
çünkü `monitor` değişiklik yoksa ajanı hiç çalıştırmaz).

---

## 5. Durum ve günlükler

**İlk koşu:** `kur.sh` son nokta dosyasını (`~/.local/state/yourkiosk-otomasyon/son-sha`)
sıfırlar; böylece i5 ilk turda **son commit'i de** inceler ve `guvenlik/inceleme` durumunu yazar.
Aksi hâlde "değişiklik yok" deyip hiçbir şey yazmaz ve haberleşme başlamamış görünür.

**Haberleşme başladı mı?** tek komut:

```bash
./otomasyon/durum
```

Son commit'lerin `guvenlik/inceleme` durumunu, açık PR'ları, etiketleri ve son i5/i3 kararını
(yorumdaki JSON bloğu) gösterir; son commit incelenmemişse "haberleşme henüz başlamadı" der.

```bash
~/.local/state/yourkiosk-otomasyon/son-sha    # en son incelenen commit
hermes cron runs <job_id>                     # son koşular + çıktı
python3 ~/calisma_konumun/yourkiosk/otomasyon/betik/topla.py --imza   # şu anki uzak HEAD
```

Yeniden incelemek için: `rm ~/.local/state/yourkiosk-otomasyon/son-sha` (sonra `--ilk` ile çalıştırın).

---

## 6. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `[topla] HATA: git deposu bulunamadı` | `--depo` veya `KIOSK_YOLU` yanlış; depo kökünü (`.git` olan klasör) verin |
| `token yok` | Dosya yolu/izni (`-rw-------`) ya da `GH_TOKEN` ortam değişkeni |
| `HTTP 404` (depo var) | Token'da depo seçili değil (*Only select repositories*) |
| `HTTP 403 Resource not accessible` | *Commit statuses: RW* / *Pull requests: RW* izni eksik |
| `degisiklik: false` hep | `git -C ~/calisma_konumun/yourkiosk fetch origin` çıktısına bakın |
| `karar dosyası GEÇERSİZ JSON` | Elle yazılmış JSON bozuk → `yaz.py --ornek` ile şablon üretin |
| Cron hiç koşmuyor | `hermes cron list` (job var mı, paused mı?), `hermes cron status`, `hermes cron doctor` |
| Ajan hiç çalışmıyor ama job koşuyor | `monitor` çıktısı değişmemiş → normal (tasarım gereği) |
| Yorum iki kez | Aynı commit'e iki kez karar yazılmış; son yazan geçerli |
| `line 2: main: command not found` | `.py` dosyasını `sh` ile çalıştırdınız → `./otomasyon/durum` (sarmalayıcı) veya `python3 otomasyon/betik/durum.py` |

---

## 6b. Branch protection durumu ve doğru sıra

```bash
./otomasyon/koruma --durum    # salt okuma: ne kurulu, son commit'te i5 var mı
```

Zorunlu kontrolü **erken** eklemek bütün PR'ları kilitler; bu yüzden komut kendini frenler:

* son commit'te `guvenlik/inceleme` **yoksa** → `DURDURULDU … --zorla` (çıkış 7),
* varsa → `--uygula --kontrol guvenlik/inceleme` güvenle çalışır.

**403 alırsanız** (bu komut yönetici yetkisi ister):

1. Token'da `Administration: Read and write` yok,
2. ya da komut **i5/i3** makinesinde çalışıyor (o token'larda Administration bilinçli olarak YOK —
   bu komut yalnız geliştirici makinesinde çalışır),
3. ya da depo private (ücretsiz hesapta protection kapalı),
4. ya da `GH_TOKEN`/`GITHUB_TOKEN` ortam değişkeni başka bir token'a işaret ediyor.

## 7. İlk gerçek koşu

1. Ben bir düzeltme commit'i push ederim (artık `main`'e doğrudan değil, **dal + PR**).
2. i5 ≤ 30 dk içinde PR yorumu + `guvenlik/inceleme` durumu yazar.
3. Ondan sonra `guvenlik/inceleme` **zorunlu kontrol** olarak branch protection'a eklenir
   (`./otomasyon/koruma --uygula --kontrol guvenlik/inceleme`).
   Şu an bilinçli olarak **ekli değil**: i5 hiç çalışmadan eklersem hiçbir PR birleşemez.
4. i5 "sorun" derse i3 ≤ 1 saat içinde karar + plan yazar; ben düzeltirim.

---

## 8. İnsanı tamamen çıkarmak (otomatik birleştirme)

Bugünkü durum: branch protection **onay sayısı 0** → insan *onayı* gerekmiyor; kalan tek insan işi
PR'daki **"Squash and merge"** tıklaması. Bunu da kaldırmanın seçenekleri:

| Seçenek | İnsan işi | Risk | Gereken |
|---|---|---|---|
| **A. Elle merge** (bugün) | PR başına 1 tık | en az | — |
| B. i5 onayı → otomatik merge | **0** | orta | i5 token'ına **Contents: Read and write** |
| C. GitHub "auto-merge" | 0 | orta | depo ayarı + Contents R/W + GraphQL |
| **D. i5 + i3 çift onay → otomatik merge** ✅ *seçildi* | **0** | **en düşük** | i3 token'ına **Contents R/W** + 2. zorunlu kontrol |

### D modu (seçildi): çift onay

| Kim | Ne yapar |
|---|---|
| **i5** | İnceleme + `guvenlik/inceleme` durumu (**birleştirme yapmaz**) |
| **i3** | İkinci inceleme + `guvenlik/karar` durumu + koşullar tamamsa **squash merge** |
| GitHub | İki durum da `success` olmadan birleştirmeye izin vermez (zorunlu kontroller) |

Kurulum:

```bash
# 1) iki zorunlu kontrol (yönetici token'ı olan makinede)
./otomasyon/koruma --uygula --kontrol "guvenlik/inceleme,guvenlik/karar"

# 2) i3 makinesinde: yazma izni + ilk koşu
./otomasyon/kontrol --rol i3 --yazma-dene   # ✓ yazma izni (Contents): HTTP 201
bash otomasyon/kur.sh i3 --cron
hermes cron run <job_id>
```

i3'ün monitörü artık **tüm açık PR'ları** izler (`--imza-prlar`); i5 onayladığı anda i3 devreye girer.

**B nasıl açılır (2 adım):**

1. i5 token'ına `Contents: Read and write` ekleyin (merge içerik yazımıdır).
2. i5 prompt'u zaten `yaz.py … --birlestir` çağırıyor → bir sonraki koşudan itibaren onay verdiği
   PR'lar otomatik birleşir.

**Koruma katmanları** (biri bile bozulsa birleşmez, nedenini PR'a yazar):

- PR taslak değil, çakışma yok (`mergeable_state == clean`),
- PR'ın head'i **incelenen commit** ile aynı (incelenmemiş kod birleşmesin),
- `guvenlik/sorun`, `duzeltme/gerekli` veya **`birlestirme/durdur`** etiketi yok — istediğiniz PR'ı
  bu etiketle durdurabilirsiniz (kill-switch),
- başka bir durum kontrolü başarısız/beklemede değil.

**Tamamen durdurmak:** i5 cron görevini duraklatın (`hermes cron pause <job_id>`) ya da PR'a
`birlestirme/durdur` etiketi ekleyin. İnceleme sürsün ama birleşmesin istiyorsanız prompt'taki
`--birlestir` bayrağını kaldırın.

**Öneri:** ilk 1–2 hafta B'yi açık tutup i5'in kararlarını (günlük konusu + PR yorumları) gözden
geçirin; yanlış onay oranı düşükse C/D'ye geçmeniz gerekmez.
