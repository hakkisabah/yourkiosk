# AGENTS.md — yourkiosk (bu depoda çalışan tüm Hermes ajanları için)

Bu dosya **depo bağlamıdır**: her makinede (geliştirici · i5 · i3) aynı şekilde okunur. Hafızaya
değil, sürümlenmiş dosyaya güvenilir — böylece üç makine aynı gerçeği görür ve bağlam PR ile
güncellenir.

> Güvenlik incelemesi yapan ajan (i5/i3) önce **`docs/GUVENLIK-BAGLAM.md`** dosyasını okur:
> güven sınırları, projeye özel otomatik-red listesi, önem eşikleri ve kabul edilmiş riskler orada.

## 1. Proje nedir

Eczane nöbet ekranı: **600+ kiosk cihazı** (Qt masaüstü + Chromium tarayıcı modu), yayın verisini
S3 + CloudFront üzerinden okur, **panel** (Vue 3 + Vuetify 3 + TS) veriyi yazar, MQTT ile "şimdi
güncelle" dürtmesi gönderilir.

| Dizin | İçerik |
|---|---|
| `kiosk/` | PyQt6 kiosk uygulaması + `tools/` + `tests/` (cihaz tarafı) |
| `web/` | tarayıcı (Chromium kiosk) modu — TS, vitest |
| `panel/` | yönetim paneli (Vue 3 + Vuetify 3 + TS + Cognito) + `infra/` yayın betikleri |
| `deploy/` | mosquitto, systemd, docker, cihaz kurulum betikleri |
| `otomasyon/` | i5/i3 iş akışı: `betik/` (nobetci, yaz, topla, karar_dogrula), `prompt/` (rol talimatları) |
| `docs/` | AWS kurulumu, maliyet, mimari, **GUVENLIK-BAGLAM.md** |

## 2. Sık kullanılan komutlar

```bash
# kiosk (Qt) testleri — offscreen
kiosk/tools/test.sh

# panel / web testleri
cd panel && npm test          # vitest
cd web   && npm test

# otomasyon
./otomasyon/kontrol                                  # ortam kontrolü
python3 otomasyon/betik/nobetci.py --rol i5 --tani    # kuyruk + yaş
python3 otomasyon/betik/nobetci.py --rol i5 --kendini-denetle
python3 otomasyon/betik/karar_dogrula.py /tmp/karar-83.json   # KARAR KAPISI
python3 -m unittest discover -s otomasyon/betik/testler -p "test_*.py"
```

`npm` kullanırken bu makinede `NODE_ENV=production` dışa aktarılmış olabilir →
`npm ci --include=dev` (aksi hâlde vite/vitest kurulmaz).

## 3. Değişmez kurallar

1. **Sır depoya girmez.** Token/parola/anahtar `~/.config/hermes-secrets/` altında (0600).
   `VITE_*` ile gelen her değer **pakete gömülür** → sır olamaz.
2. **`main` korumalı:** doğrudan push yok. Her değişiklik dal + PR.
   `guvenlik/inceleme` (i5) ve `guvenlik/karar` (i3) durumları **zorunlu**.
3. **Kendi işini onaylamak yok.** Kodu yazan ajan/makine o PR'a onay veremez.
4. **i5/i3 kod yazmaz**, commit/push/birleştirme yapmaz (i3'ün birleştirmesi `--cift-onay` ile).
5. **Doküman sayıları koddan türetilir.** Süre/sınır değişince README/NODET/config yorumları da
   aynı PR'da güncellenir — bayat sayı "bildirdim ama değişmedi" algısının kaynağıydı.
6. **Davranış değiştiyse test de gelir.** Test hatayı gerçekten yakalıyor mu, göster.
7. Yanıtlar ve commit mesajları **Türkçe**; kod içi yorumlar Türkçe, tanımlayıcılar İngilizce.

## 4. Kapı akışı (i5/i3)

```
nobetçi (15 sn ETag yoklaması, en eski PR önce)
   → i5: 12 alanın tamamını denetler → /tmp/karar-<no>.json
   → yaz.py  → KARAR KAPISI (karar_dogrula) → geçmezse GitHub'a HİÇBİR şey yazılmaz
                  ↑ fail-closed: kararsızsan "sorun" + "doğrulanmalı", asla "onay"
   → i3: i5 bulgularını yerinde doğrular, kendi taramasını yapar → karar + birleştirme
```

Karar JSON'unda **zorunlu**: `makine`, `pr`, `sha`, `karar`, `onem`, `ozet`, `bulgular`
(`dosya`+`satir`+`onem`+`aciklama`), **`denetlenen`** (i5: 12 alanın tamamı, i3: en az 8'i ve
`gömülü sır`/`kimlik/yetki`/`test kanıtı`).

## 5. Bağlam nerede tutulur

| Bilgi | Yeri |
|---|---|
| Proje kuralları, komutlar | bu dosya |
| Tehdit modeli, otomatik-red listesi, önem eşikleri, kabul edilmiş riskler | `docs/GUVENLIK-BAGLAM.md` |
| Rol talimatları (detaylı denetim adımları) | `otomasyon/prompt/i5-guvenlik.md`, `i3-karar.md` |
| Cihaz tarafı sertleştirme | `kiosk/GUVENLIK.md` |
| AWS kurulumu ve kimlikler | `docs/AWS-KURULUM.md` |
| Maliyet/kota | `docs/ONBELLEK-VE-MALIYET.md`, `panel/MAALIYET.md` |

Kişisel ajan hafızası bu bilgilerin **yeri değildir**: makineye bağlıdır, diff'lenemez, diğer iki
makinede yoktur. Bir kural kalıcı olacaksa buraya yazılır.
